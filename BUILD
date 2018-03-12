config_setting(
    name = "darwin",
    values = {"cpu": "darwin"},
    visibility = ["//visibility:public"],
)

# The authoritative repo python interpreter. This is not generated by
# bazel. Instead, the script tools/bootstrap.sh creates the virtualenv.
filegroup(
    name = "python_runtime",
    srcs = glob(
        ["venv/phd/**"],
        exclude = [
            # Illegal as Bazel labels but are not required by pip.
            "**/launcher manifest.xml",
            "**/setuptools/*.tmpl",
            "**/nbconvert/preprocessors/tests/files/*.ipynb",
        ],
    ),
    visibility = ["//visibility:public"],
)

py_runtime(
    name = "python3.6",
    files = [":python_runtime"],
    interpreter = "venv/phd/bin/python3.6",
    visibility = ["//visibility:public"],
)