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

#include "gpu/clcheck/kernel_arg_value.h"

#include "third_party/opencl/cl.hpp"

#include "gpu/clcheck/opencl_type.h"
#include "labm8/cpp/logging.h"
#include "labm8/cpp/string.h"

namespace gpu {
namespace clcheck {

// A scalar argument.
template <typename T>
class ScalarKernelArgValue : public KernelArgValue {
 public:
  explicit ScalarKernelArgValue(const T &value) : value_(value) {}

  virtual bool operator==(const KernelArgValue *const rhs) const override {
    auto rhs_ptr = dynamic_cast<const ScalarKernelArgValue *const>(rhs);
    if (!rhs_ptr) {
      return false;
    }

    return opencl_type::Equal(value(), rhs_ptr->value());
  }

  virtual bool operator!=(const KernelArgValue *const rhs) const override {
    return !(*this == rhs);
  };

  virtual void SetAsArg(cl::Kernel *kernel, size_t arg_index) override {
    kernel->setArg(arg_index, value());
  };

  virtual void CopyToDevice(const cl::CommandQueue &queue,
                            ProfilingData *profiling) override{};

  virtual std::unique_ptr<KernelArgValue> CopyFromDevice(
      const cl::CommandQueue &queue, ProfilingData *profiling) override {
    return std::make_unique<ScalarKernelArgValue>(value());
  }

  virtual string ToString() const override {
    return opencl_type::ToString(value());
  }

  virtual size_t SizeInBytes() const override { return sizeof(T); }
  virtual size_t Size() const override { return 1; }

  const T &value() const { return value_; }
  T &value() { return value_; }

 private:
  T value_;
};

}  // namespace clcheck
}  // namespace gpu
