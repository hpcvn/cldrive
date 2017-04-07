# Copyright (C) 2017 Chris Cummins.
#
# This file is part of cldrive.
#
# Cldrive is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Cldrive is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cldrive.  If not, see <http://www.gnu.org/licenses/>.
#
import pickle
import sys

from pkg_resources import resource_filename
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile

import numpy as np
import pyopencl as cl

from cldrive import *


class NonTerminatingError(RuntimeError):
    """ thrown if kernel executions fails to complete before timeout """
    pass


class NDRange(namedtuple('NDRange', ['x', 'y', 'z'])):
    """
    A 3 dimensional NDRange tuple. Has components x,y,z.
    """
    __slots__ = ()

    def __repr__(self) -> str:
        return f"[{self.x}, {self.y}, {self.z}]"

    @property
    def product(self) -> int:
        """ linear product is x * y * z """
        return self.x * self.y * self.z

    def __eq__(self, rhs: 'NDRange') -> bool:
        return (self.x == rhs.x and self.y == rhs.y and self.z == rhs.z)

    def __gt__(self, rhs: 'NDRange') -> bool:
        return (self.product > rhs.product and
                self.x >= rhs.x and self.y >= rhs.y and self.z >= rhs.z)

    def __ge__(self, rhs: 'NDRange') -> bool:
        return self == rhs or self > rhs


def drive(env: OpenCLEnvironment, src: str, inputs: np.array,
          gsize: NDRange, lsize: NDRange, timeout: int=-1,
          optimizations: bool=True, profiling: bool=False, debug: bool=False):
    """
    OpenCL kernel.

    Arguments:
        env (OpenCLEnvironment): The OpenCL environment to run the
            kernel in.
        src (str): The OpenCL kernel source.
        optimizations (bool, optional): Whether to enable or disbale OpenCL
            compiler optimizations.
        profiling (bool, optional): If true, record OpenCLevent times for
        timeout (int, optional): Cancel execution if it has not completed
            after this many seconds. A value <= 0 means never time out.
        debug (bool, optional): If true, silence the OpenCL compiler.
        data transfers and kernel executions.

    Returns:
        np.array: A numpy array of the same shape as the inputs, with the
            values after running the OpenCL kernel.

    Raises:
        ValueError: if input types are incorrect.
        TypeError: if an input is of an incorrect type.
        LogicError: if the input types do not match OpenCL kernel types.
        RuntimeError: if OpenCL program fails to build or run.

    TODO:
        * Implement profiling
    """
    def log(*args, **kwargs):
        if debug:
            print(*args, **kwargs, file=sys.stderr)

    # assert input types
    assert_or_raise(isinstance(env, OpenCLEnvironment), ValueError,
                    "env argument is of incorrect type")
    assert_or_raise(isinstance(src, str), ValueError,
                    "source is not a string")

    # validate global and local sizes
    assert_or_raise(len(gsize) == 3, TypeError)
    assert_or_raise(len(lsize) == 3, TypeError)
    gsize, lsize = NDRange(*gsize), NDRange(*lsize)

    assert_or_raise(gsize.product >= 1, ValueError,
                    f"Scalar global size {gsize.product} must be >= 1")
    assert_or_raise(lsize.product >= 1, ValueError,
                    f"Scalar local size {lsize.product} must be >= 1")
    assert_or_raise(gsize >= lsize, ValueError,
                    f"Global size {gsize} must be larger than local size {lsize}")

    # parse args in this process since we want to preserve the sueful exception
    # type
    args = extract_args(src)

    # check that the number of inputs is correct
    args_with_inputs = [i for i, arg in enumerate(args) if not arg.is_local]
    assert_or_raise(len(args_with_inputs) == len(inputs), ValueError,
                    "Kernel expects {} inputs, but {} were provided".format(
                        len(args_with_inputs), len(inputs)))

    # copy inputs into the expected data types
    data = np.array([np.array(d).astype(a.numpy_type)
                     for d, a in zip(inputs, args)])

    job = {
        "env": env,
        "src": src,
        "args": args,
        "data": data,
        "gsize": gsize,
        "lsize": lsize,
        "optimizations": optimizations,
        "profiling": profiling
    }

    with NamedTemporaryFile('rb+', prefix='cldrive-', suffix='.job') as tmpfile:
        porcelain_job_file = tmpfile.name

        # write job file
        pickle.dump(job, tmpfile)
        tmpfile.flush()

        # enforce timeout using `timeout' command
        if timeout > 0:
            cli = ["timeout", "--signal=9", str(int(timeout))]
        else:
            cli = []
        cli += [sys.executable, __file__, porcelain_job_file]

        cli_str = " ".join(cli)
        log("Porcelain invocation:", cli_str)

        # fork and run
        process = Popen(cli, stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()

        log(stdout.decode('utf-8'))
        log(stderr.decode('utf-8'))

        # test for non-zero exit codes. The porcelain subprocess catches
        # exceptions and executes gracefully, so a non-zero return code is
        # indicative of a more serious problem
        KILL_SIGNAL = -9
        if timeout > 0 and process.returncode == KILL_SIGNAL:
            raise NonTerminatingError(
                f"porcelain subprocess failed to complete within {timeout} seconds")
        elif process.returncode:
            raise RuntimeError(
                f"porcelain subprocess exited with status code {process.returncode}")

        # read result
        tmpfile.seek(0)

        rets = pickle.load(tmpfile)
        outputs = rets["outputs"]
        err = rets["err"]

        if err:
            raise err
        else:
            return outputs


def __porcelain_exec(path: str) -> np.array:
    def log(*args, **kwargs):
        print(*args, **kwargs, file=sys.stderr)

    with open(path, 'rb') as infile:
        job = pickle.load(infile)

    env = job["env"]
    src = job["src"]
    args = job["args"]
    data = job["data"]
    gsize = job["gsize"]
    lsize = job["lsize"]
    optimizations = job["optimizations"]
    profiling = job["profiling"]

    ctx, queue = env.ctx_queue

    # CLSmith cl_launcher compatible logging output. See:
    #    https://github.com/ChrisCummins/CLSmith/blob/master/src/CLSmith/cl_launcher.c
    device = queue.get_info(cl.command_queue_info.DEVICE)
    device_name = device.get_info(cl.device_info.NAME)

    platform = device.get_info(cl.device_info.PLATFORM)
    platform_name = platform.get_info(cl.platform_info.VENDOR)

    log(f"Platform: {platform_name}")
    log(f"Device: {device_name}")

    log(f"3-D global size {gsize.product} = {gsize}")
    log(f"3-D local size {lsize.product} = {lsize}")

    # Additional logging output for inputs:
    log("Number of kernel arguments:", len(args))
    log("Kernel arguments:", ", ".join(str(a) for a in args))
    log("Kernel input elements:", ", ".join(str(x.size) for x in data))

    # OpenCL compiler flags
    if optimizations:
        build_flags = []
        log("OpenCL optimizations: on")
    else:
        build_flags = ['-cl-opt-disable']
        log("OpenCL optimizations: off")

    # parent process determines whether or not to silence this output
    os.environ['PYOPENCL_COMPILER_OUTPUT'] = '1'

    try:
        program = cl.Program(ctx, src).build(build_flags)
    except cl.RuntimeError as e:
        raise RuntimeError from e

    kernels = program.all_kernels()
    # extract_args() should already have raised an error if there's more
    # than one kernel:
    assert(len(kernels) == 1)
    kernel = kernels[0]

    # buffer size is the scalar global size, or the size of the largest
    # input, whichever is bigger
    if len(data):
        buf_size = max(gsize.product, *[x.size for x in data])
    else:
        buf_size = gsize.product

    # assemble argtuples
    ArgTuple = namedtuple('ArgTuple', ['hostdata', 'devdata'])
    argtuples = []
    data_i = 0
    for i, arg in enumerate(args):
        if arg.is_global:
            data[data_i] = data[data_i].astype(arg.numpy_type)
            hostdata = data[data_i]
            # determine flags to pass to OpenCL buffer creation:
            flags = cl.mem_flags.COPY_HOST_PTR
            if arg.is_const:
                flags |= cl.mem_flags.READ_ONLY
            else:
                flags |= cl.mem_flags.READ_WRITE
            buf = cl.Buffer(ctx, flags, hostbuf=hostdata)

            devdata, data_i = buf, data_i + 1
        elif arg.is_local:
            nbytes = buf_size * arg.vector_width * arg.numpy_type.itemsize
            buf = cl.LocalMemory(nbytes)

            hostdata, devdata = None, buf
        elif not arg.is_pointer:
            hostdata = None
            devdata, data_i = arg.numpy_type(data[data_i]), data_i + 1
        else:
            # argument is neither global or local, but is a pointer?
            raise ValueError(f"unknown argument type '{arg}'")
        argtuples.append(ArgTuple(hostdata=hostdata, devdata=devdata))

    assert_or_raise(len(data) == data_i, ValueError,
                    "failed to set input arguments")

    # clear any existing tasks in the command queue
    queue.flush()

    # copy inputs from host -> device
    for argtuple in argtuples:
        if argtuple.hostdata is not None:
            cl.enqueue_copy(queue, argtuple.devdata, argtuple.hostdata,
                            is_blocking=False)

    kernel_args = [argtuple.devdata for argtuple in argtuples]

    try:
        kernel.set_args(*kernel_args)
    except cl.LogicError as e:
        raise ValueError(e)

    # run the kernel
    kernel(queue, gsize, lsize, *kernel_args)

    # copy data from device -> host
    for arg, argtuple in zip(args, argtuples):
        # const arguments are unmodified
        if argtuple.hostdata is not None and not arg.is_const:
            cl.enqueue_copy(queue, argtuple.hostdata, argtuple.devdata,
                            is_blocking=False)

    # wait for OpenCL commands to complete
    queue.flush()

    return data


def __porcelain(path: str) -> None:
    """
    Run OpenCL kernel. Invoke as a subprocess.
    """
    outputs = None
    err = None

    try:
        outputs = __porcelain_exec(path)
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        err = e

    with open(path, 'wb') as outfile:
        pickle.dump({
            "outputs": outputs,
            "err": err
        }, outfile)


# entry point for porcelain incvocation
if __name__ == "__main__":
    __porcelain(sys.argv[1])
