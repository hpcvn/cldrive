// Copyright (c) 2016-2020 Chris Cummins.
// This file is part of clcheck.
//
// clcheck is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// clcheck is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with clcheck.  If not, see <https://www.gnu.org/licenses/>.
#include "gpu/clcheck/libclcheck.h"

#include "gpu/clcheck/kernel_arg_value.h"
#include "gpu/clcheck/kernel_driver.h"
#include "gpu/clinfo/libclinfo.h"

#include "labm8/cpp/logging.h"
#include "labm8/cpp/status.h"
#include "labm8/cpp/statusor.h"

#include "absl/strings/str_cat.h"
#include "absl/strings/str_format.h"
#include "absl/strings/strip.h"
#include "absl/time/clock.h"
#include "absl/time/time.h"

#define LOG_CL_ERROR(level, error)                                  \
  LOG(level) << "OpenCL exception: " << error.what() << ", error: " \
             << labm8::gpu::clinfo::OpenClErrorString(error.err());

namespace gpu {
namespace clcheck {

namespace {

// Attempt to build OpenCL program.
labm8::StatusOr<cl::Program> BuildOpenClProgram(
    const std::string& opencl_kernel, const cl::Context& context,
    const string& cl_build_opts) {
  auto start_time = absl::Now();
  try {
    // Assemble the build options. We need -cl-kernel-arg-info so that we can
    // read the kernel signatures.
    string all_build_opts = "-cl-kernel-arg-info ";
    absl::StrAppend(&all_build_opts, cl_build_opts);
    labm8::TrimRight(all_build_opts);

    cl::Program program(context, opencl_kernel);
    program.build(context.getInfo<CL_CONTEXT_DEVICES>(),
                  all_build_opts.c_str());
    auto end_time = absl::Now();
    auto duration = (end_time - start_time) / absl::Milliseconds(1);
    LOG(INFO) << "clBuildProgram() with options '" << all_build_opts
              << "' completed in " << duration << " ms";
    return program;
  } catch (cl::Error e) {
    LOG_CL_ERROR(WARNING, e);
    return labm8::Status(labm8::error::Code::INVALID_ARGUMENT,
                         "clBuildProgram failed");
  }
}

}  // namespace

Cldrive::Cldrive(CldriveInstance* instance, int instance_num)
    : instance_(instance),
      instance_num_(instance_num),
      device_(labm8::gpu::clinfo::GetOpenClDeviceOrDie(instance->device())) {}

void Cldrive::RunOrDie(Logger& logger) {
  try {
    DoRunOrDie(logger);
  } catch (cl::Error error) {
    LOG(FATAL) << "Unhandled OpenCL exception.\n"
               << "    Raised by:  " << error.what() << '\n'
               << "    Error code: " << error.err() << " ("
               << labm8::gpu::clinfo::OpenClErrorString(error.err()) << ")\n"
               << "This is a bug! Please report to "
               << "<https://github.com/ChrisCummins/clcheck/issues>.";
  }
}

void Cldrive::DoRunOrDie(Logger& logger) {
  cl::Context context(device_);
  cl::CommandQueue queue(context,
                         /*devices=*/context.getInfo<CL_CONTEXT_DEVICES>()[0],
                         /*properties=*/CL_QUEUE_PROFILING_ENABLE);

  // Compile program or fail.
  labm8::StatusOr<cl::Program> program_or = BuildOpenClProgram(
      string(instance_->opencl_src()), context, instance_->build_opts());
  if (!program_or.ok()) {
    LOG(ERROR) << "OpenCL program compilation failed!";
    instance_->set_outcome(CldriveInstance::PROGRAM_COMPILATION_FAILURE);
    logger.RecordLog(instance_, /*kernel_instance=*/nullptr, /*run=*/nullptr,
                     /*log=*/nullptr);
    return;
  }
  cl::Program program = program_or.ValueOrDie();

  std::vector<cl::Kernel> kernels;
  program.createKernels(&kernels);

  if (!kernels.size()) {
    LOG(ERROR) << "OpenCL program contains no kernels!";
    instance_->set_outcome(CldriveInstance::NO_KERNELS_IN_PROGRAM);
    return;
  }

  for (auto& kernel : kernels) {
    KernelDriver(context, queue, kernel, instance_, instance_num_)
        .RunOrDie(logger);
  }

  instance_->set_outcome(CldriveInstance::PASS);

  // TODO: explain
  for (auto kernel : kernels) {
    cl_kernel k = *(cl_kernel*)&kernel;
    ::clReleaseKernel(k);
  }
}

}  // namespace clcheck
}  // namespace gpu
