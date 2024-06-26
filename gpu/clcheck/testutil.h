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
#pragma once

#include "gpu/clcheck/global_memory_arg_value.h"
#include "gpu/clcheck/kernel_arg_value.h"
#include "gpu/clcheck/proto/clcheck.pb.h"
#include "gpu/clcheck/scalar_kernel_arg_value.h"

#include "third_party/opencl/cl.hpp"

namespace gpu {
namespace clcheck {
namespace test {

// Create an OpenCL kernel from the given string else abort.
//
// The string must contain the OpenCL source for a single kernel,
// e.g. cl::Kernel kernel = CreateClKernel("kernel void A() {}");
cl::Kernel CreateClKernel(const string& opencl_kernel);

// Downcast a KernelArgValue to the given type.
//
// If the cast cannot be made, test aborts.
template <typename T>
T* Downcast(KernelArgValue* t) {
  CHECK(t) << "KernelArgValue pointer is null";
  auto pointer = dynamic_cast<T*>(t);
  CHECK(pointer) << "Failed to cast KernelArgValue pointer";
  return pointer;
}

DynamicParams MakeParams(size_t global_size, size_t local_size = 1);

}  // namespace test
}  // namespace clcheck
}  // namespace gpu
