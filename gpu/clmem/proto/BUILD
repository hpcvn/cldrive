# Copyright (c) 2016-2020 Chris Cummins.
# This file is part of cldrive.
#
# cldrive is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cldrive is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cldrive.  If not, see <https://www.gnu.org/licenses/>.
load("@build_stack_rules_proto//python:python_proto_library.bzl", "python_proto_library")

package(default_visibility = ["//visibility:public"])

proto_library(
    name = "clmem_pb",
    srcs = ["clmem.proto"],
    deps = [
        "//gpu/clinfo/proto:clinfo_pb",
        "//gpu/libcecl/proto:libcecl_pb",
    ],
)

cc_proto_library(
    name = "clmem_py_cc",
    deps = [":clmem_pb"],
)

python_proto_library(
    name = "clmem_pb_py",
    deps = [":clmem_pb"],
)
