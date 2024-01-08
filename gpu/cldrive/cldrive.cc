// Main entry point for cldrive command line executable.
//
// Usage summary:
//   cldrive --srcs=<opencl_sources> --envs=<opencl_devices>
//       --gsize=<gsize> --lsize=<lsize> --output_format=(txt|pb|pbtxt)
//
// Run with `--help` argument to see full usage options.
//
// Copyright (c) 2016-2020 Chris Cummins.
// This file is part of cldrive.
//
// cldrive is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// cldrive is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with cldrive.  If not, see <https://www.gnu.org/licenses/>.
#include "gpu/cldrive/libcldrive.h"
#include "gpu/cldrive/mem_analysis_util.h"
#include "gpu/cldrive/kernel_info_util.h"

#include "gpu/cldrive/logger.h"
#include "gpu/cldrive/proto/cldrive.pb.h"
#include "gpu/clinfo/libclinfo.h"

#include "labm8/cpp/app.h"
#include "labm8/cpp/logging.h"

#include "absl/strings/str_split.h"
#include "boost/filesystem.hpp"
#include "boost/filesystem/fstream.hpp"
#include "gflags/gflags.h"

#include <sstream>
#include <json/json.h>

namespace {
// Split a string into a vector of comma separated strings, e.g.
//     'a,b' -> 'a', 'b'
//     'ab' -> 'ab'
std::vector<string> SplitCommaSeparated(const string& str) {
  std::vector<absl::string_view> str_paths =
      absl::StrSplit(str, ',', absl::SkipEmpty());
  return std::vector<string>(str_paths.begin(), str_paths.end());
}

// Read the entire contents of a file to string or abort.
string ReadFileOrDie(const string& path) {
  const boost::filesystem::path fs_path(path);
  CHECK(boost::filesystem::is_regular_file(fs_path))
      << "Not a regular file: '" << path << "'";
  boost::filesystem::ifstream istream(fs_path);
  CHECK(istream.is_open()) << "Failed to open: '" << path << "'";

  std::stringstream buffer;
  buffer << istream.rdbuf();
  return buffer.str();
}

}  // anonymous namespace

// Flag definitions ------------------------------------

DEFINE_string(srcs, "", "A comma separated list of OpenCL source files.");
static bool ValidateSrcs(const char* flagname, const string& value) {
  for (auto str_path : SplitCommaSeparated(value)) {
    // string str_path(str_path_view);
    boost::filesystem::path path(str_path);
    if (!boost::filesystem::is_regular_file(path)) {
      LOG(FATAL) << "File not found: " << value;
    }
  }

  return true;
}
DEFINE_validator(srcs, &ValidateSrcs);

DEFINE_string(mem_analysis_dir, "mem_analysis_info", "The directory to store the memory analysis information, "
                                                      "each source file corresponds to a json file with same name in this directory. "
                                                      "Example: if the source file is /path/to/file.cl, "
                                                      "then the memory analysis file is /path/to/mem_analysis_info/file.json");
static bool ValidateMemAnalysis(const char* flagname, const string& value) {
  for (auto str_path : SplitCommaSeparated(FLAGS_srcs)) {
    if (!gpu::cldrive::mem_analysis::isMemAnalysisFileExists(str_path, value)) {
      LOG(WARNING) << "Memory analysis file not found for source file: " << str_path << ". Using default memory analysis setting."
                   << ". Please run clmem first to generate the memory analysis file, then put it in " << value << " directory.";
    }
  }

  return true;
}
DEFINE_validator(mem_analysis_dir, &ValidateMemAnalysis);

DEFINE_string(envs, "",
              "A comma separated list of OpenCL devices to use. Use "
              "'--clinfo' argument to print a list of available devices. If "
              "not provided, all available OpenCL devices will be used.");
static bool ValidateEnvs(const char* flagname, const string& value) {
  for (auto env : SplitCommaSeparated(value)) {
    try {
      labm8::gpu::clinfo::GetOpenClDevice(env);
    } catch (std::invalid_argument e) {
      LOG(ERROR) << "Available OpenCL environments:";
      auto devices = labm8::gpu::clinfo::GetOpenClDevices();
      for (int i = 0; i < devices.device_size(); ++i) {
        LOG(ERROR) << "    " << devices.device(i).name();
      }
      LOG(FATAL) << "OpenCL environment '" << env << "' not found";
    }
  }
  return true;
}
DEFINE_validator(envs, &ValidateEnvs);

DEFINE_string(output_format, "csv",
              "The output format. One of: {csv,pb,pbtxt}.");
static bool ValidateOutputFormat(const char* flagname, const string& value) {
  if (value.compare("csv") && value.compare("pb") && value.compare("pbtxt")) {
    LOG(FATAL) << "Illegal value for --" << flagname << ". Must be one of: "
               << "{csv,pb,pbtxt}";
  }
  return true;
}
DEFINE_validator(output_format, &ValidateOutputFormat);

DEFINE_int32(gsize, 1024,
             "The global size to drive each kernel with. Buffers of this size "
             "are allocated and transferred for array arguments, and this many "
             "work items are instantiated.");
DEFINE_int32(lsize_x, 128, "The local (work group) size in first dimension. lsize_x*lsize_y*lsize_z must be <= gsize.");
DEFINE_int32(lsize_y, 1, "The local (work group) size in second dimension. lsize_x*lsize_y*lsize_z must be <= gsize.");
DEFINE_int32(lsize_z, 1, "The local (work group) size in third dimension. lsize_x*lsize_y*lsize_z must be <= gsize.");
static bool ValidateDynamicParams(const char* flagname, const GFLAGS_NAMESPACE::int32 value) {
  GFLAGS_NAMESPACE::int32 gsize = value;
  GFLAGS_NAMESPACE::int32 lsize_x = FLAGS_lsize_x;
  GFLAGS_NAMESPACE::int32 lsize_y = FLAGS_lsize_y;
  GFLAGS_NAMESPACE::int32 lsize_z = FLAGS_lsize_z;
  if ((int64_t)gsize < (int64_t) lsize_x * lsize_y * lsize_z) {
    LOG(FATAL) << "Global size must be greater than or equal to local size. Got: "
                << "gsize: " << gsize << ", lsize_x*lsize_y*lsize_z: " <<  (int64_t) lsize_x * lsize_y * lsize_z;
  }
  return true;
}
DEFINE_validator(gsize, &ValidateDynamicParams);

DEFINE_string(cl_build_opt, "", "Build options passed to clBuildProgram().");
DEFINE_int32(num_runs, 30, "The number of runs per kernel.");
DEFINE_bool(clinfo, false, "List the available devices and exit.");
DEFINE_bool(kernelinfo, false, "List the kernel arguments and exit.");

// End flag definitions ------------------------------------

namespace gpu {
namespace cldrive {

std::unique_ptr<Logger> MakeLoggerFromFlags(
    std::ostream& ostream, const CldriveInstances* const instances) {
  if (!FLAGS_output_format.compare("pb")) {
    return std::make_unique<ProtocolBufferLogger>(std::cout, instances,
                                                  /*text_format=*/false);
  } else if (!FLAGS_output_format.compare("pbtxt")) {
    return std::make_unique<ProtocolBufferLogger>(std::cout, instances,
                                                  /*text_format=*/true);
  } else if (!FLAGS_output_format.compare("csv")) {
    return std::make_unique<CsvLogger>(std::cout, instances);
  } else {
    CHECK(false) << "unreachable!";
    return nullptr;
  }
}

}  // namespace cldrive
}  // namespace gpu

namespace {

// Look up OpenCL devices from a comma separated list of names. If the string
// is empty, all available devices are returned.
std::vector<::gpu::clinfo::OpenClDevice> GetDevicesFromCommaSeparatedString(
    const string& str) {
  std::vector<::gpu::clinfo::OpenClDevice> devices;

  if (FLAGS_envs.empty()) {
    auto devices_proto = labm8::gpu::clinfo::GetOpenClDevices();
    for (int i = 0; i < devices_proto.device_size(); ++i) {
      devices.push_back(devices_proto.device(i));
    }
  } else {
    for (auto device_name : SplitCommaSeparated(FLAGS_envs)) {
      devices.push_back(
          labm8::gpu::clinfo::GetOpenClDeviceProto(device_name).ValueOrDie());
    }
  }

  return devices;
}

}  // namespace

int main(int argc, char** argv) {
  labm8::InitApp(&argc, &argv, "Drive arbitrary OpenCL kernels.");

  // Special case handling for --clinfo argument which prints to stdout then
  // quits.
  if (FLAGS_clinfo) {
    auto devices = labm8::gpu::clinfo::GetOpenClDevices();
    for (int i = 0; i < devices.device_size(); ++i) {
      std::cout << devices.device(i).name() << std::endl;
    }
    return 0;
  }

  if (FLAGS_kernelinfo) {
    cl::Device device = labm8::gpu::clinfo::GetOpenClDeviceOrDie(labm8::gpu::clinfo::GetOpenClDevices().device(0));
    std::string res = "{";
    for (auto path : SplitCommaSeparated(FLAGS_srcs)) {
      res +=  "\"" + path + "\": ";
      string opencl_src = ReadFileOrDie(path);
      res += gpu::cldrive::util::GetKernelInfoOrDie(opencl_src, "", device) + ",";
    }
    res.back() ='}';
    std::cout << res << std::endl;
    return 0;
  }

  // Check that required flags are set. We can't check this in the flag
  // validator functions as they are only required if the early-exit flags
  // above are not set.
  if (FLAGS_srcs.empty()) {
    LOG(FATAL) << "Flag --srcs must be set";
  }

  auto devices = GetDevicesFromCommaSeparatedString(FLAGS_envs);

  // Create instances proto.
  gpu::cldrive::CldriveInstances instances;
  gpu::cldrive::CldriveInstance* instance = instances.add_instance();
  instance->set_build_opts(FLAGS_cl_build_opt);
  auto dp = instance->add_dynamic_params();
  dp->set_global_size_x(FLAGS_gsize);
  dp->set_local_size_x(FLAGS_lsize_x);
  dp->set_local_size_y(FLAGS_lsize_y);
  dp->set_local_size_z(FLAGS_lsize_z);
  instance->set_min_runs_per_kernel(FLAGS_num_runs);

  // Parse logger flag.
  std::unique_ptr<gpu::cldrive::Logger> logger =
      gpu::cldrive::MakeLoggerFromFlags(std::cout, &instances);

  int instance_num = 0;
  for (auto path : SplitCommaSeparated(FLAGS_srcs)) {
    std::map<int,int> memAnalysis = gpu::cldrive::mem_analysis::getMemAnalysisInfo(path, FLAGS_mem_analysis_dir, FLAGS_gsize, FLAGS_lsize_x*FLAGS_lsize_y*FLAGS_lsize_z);
    
    logger->StartNewInstance();
    instance->set_opencl_src(ReadFileOrDie(path));
    instance->set_mem_filepath(gpu::cldrive::mem_analysis::getMemAnalysisFilePath(path, FLAGS_mem_analysis_dir).string());

    for (size_t i = 0; i < devices.size(); ++i) {
      // Reset fields from previous loop iterations.
      instance->clear_outcome();
      instance->clear_kernel();

      *instance->mutable_device() = devices[i];

      gpu::cldrive::Cldrive(instance, instance_num).RunOrDie(*logger);
    }

    ++instance_num;
  }

  return 0;
}
