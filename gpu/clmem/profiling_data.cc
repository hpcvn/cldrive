// Copyright (c) 2016-2020 Chris Cummins.
// This file is part of clmem.
//
// clmem is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// clmem is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with clmem.  If not, see <https://www.gnu.org/licenses/>.
#include "gpu/clmem/profiling_data.h"

namespace gpu {
namespace clmem {

labm8::int64 GetElapsedNanoseconds(const cl::Event& event) {
  event.wait();
  cl_ulong start = event.getProfilingInfo<CL_PROFILING_COMMAND_QUEUED>();
  cl_ulong end = event.getProfilingInfo<CL_PROFILING_COMMAND_END>();
  return static_cast<labm8::int64>(end - start);
}

}  // namespace clmem
}  // namespace gpu
