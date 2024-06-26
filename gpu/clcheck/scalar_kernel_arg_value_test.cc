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
#include "gpu/clcheck/scalar_kernel_arg_value.h"

#include "labm8/cpp/port.h"
#include "labm8/cpp/test.h"

namespace gpu {
namespace clcheck {
namespace {

TEST(ScalarKernelArgValue, IntValuesAreEqual) {
  ScalarKernelArgValue<labm8::int32> a(5);
  ScalarKernelArgValue<labm8::int32> b(5);
  EXPECT_EQ(a, &b);
}

TEST(ScalarKernelArgValue, DifferentIntValuesAreNotEqual) {
  ScalarKernelArgValue<labm8::int32> a(5);
  ScalarKernelArgValue<labm8::int32> b(6);
  EXPECT_NE(a, &b);
}

TEST(ScalarKernelArgValue, FloatValuesAreEqual) {
  ScalarKernelArgValue<float> a(1.25);
  ScalarKernelArgValue<float> b(1.25);
  EXPECT_EQ(a, &b);
}

TEST(ScalarKernelArgValue, DifferentFloatValuesAreNotEqual) {
  ScalarKernelArgValue<float> a(1.25);
  ScalarKernelArgValue<float> b(1.35);
  EXPECT_NE(a, &b);
}

TEST(ScalarKernelArgValue, DifferentTypesWithSameValueAreNotEqual) {
  ScalarKernelArgValue<labm8::int32> a(5);
  ScalarKernelArgValue<labm8::int64> b(5);
  EXPECT_NE(a, &b);
}

TEST(ScalarKernelArgValue, IntValueToString) {
  EXPECT_EQ(ScalarKernelArgValue<labm8::int32>(3).ToString(), string("3"));
  EXPECT_EQ(ScalarKernelArgValue<labm8::int64>(3).ToString(), string("3"));
}

TEST(ScalarKernelArgValue, FloatValueToString) {
  EXPECT_EQ(ScalarKernelArgValue<float>(3.5).ToString(), string("3.5"));
  EXPECT_EQ(ScalarKernelArgValue<float>(0.12345).ToString(), string("0.12345"));
}

}  // anonymous namespace
}  // namespace clcheck
}  // namespace gpu

TEST_MAIN();
