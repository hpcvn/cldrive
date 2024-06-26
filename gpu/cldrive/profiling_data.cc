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
#include "gpu/cldrive/profiling_data.h"

namespace gpu {
namespace cldrive {

labm8::int64 GetElapsedNanoseconds(const cl::Event& event) {
  event.wait();
  cl_ulong start = event.getProfilingInfo<CL_PROFILING_COMMAND_START>();
  cl_ulong end = event.getProfilingInfo<CL_PROFILING_COMMAND_END>();
  return static_cast<labm8::int64>(end - start);
}

}  // namespace cldrive
}  // namespace gpu
