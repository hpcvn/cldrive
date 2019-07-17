"""A script which exports the subset of this repository required for target(s).

This project is getting large. This has two major downsides:
  * Fresh checkouts of the git repository take longer and consume more space.
  * The large number of packages is confusing to newcomers.

I feel like there's a 90-10 rule that applies to this repo: 90% of people who
checkout this repo only need 10% of the code contained within it.
This script provides a way to export that 10%.
"""
import os

import contextlib
import datetime
import git
import github as github_lib
import glob
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import typing

import getconfig
from datasets.github import api
from labm8 import app
from labm8 import bazelutil
from labm8 import fs

FLAGS = app.FLAGS

app.DEFINE_list('targets', [], 'The bazel target(s) to export.')
app.DEFINE_list(
    'extra_files', [],
    'A list of additional files to export. Each element in the '
    'list is either a relative path to export, or a mapping of '
    'relative paths in the form <src>:<dst>. E.g. '
    '`foo.py:bar/baz.txt` will export file `foo.py` to '
    'destination `bar/baz.txt`.')
app.DEFINE_string('destination', '/tmp/phd/tools/source_tree/export',
                  'The destination directory to export to.')
app.DEFINE_string('github_repo', None, 'Name of a GitHub repo to export to.')
app.DEFINE_boolean('github_repo_create_private', True,
                   'Whether to create new GitHub repos as private.')

BAZEL_WRAPPER = bazelutil.DataPath(
    'phd/tools/source_tree/data/bazel_wrapper.py')

# A list of relative paths to include in every export. Glob patterns are
# expanded.
ALWAYS_INCLUDED_FILES = [
    '.bazelrc',  # Not strictly required, but provides consistency.
    'configure',  # Needed to generate config proto.
    'BUILD',  # Top-level BUILD file is always needed.
    'WORKSPACE',
    'README.md',
    'tools/bzl/*',  # Implicit dependency of WORKSPACE file.
    'tools/BUILD',  # Needed by //tools/bzl:maven_jar.bzl.
    'tools/download_file.py',  # Needed by //tools/bzl:maven_jar.bzl.
    'tools/util.py',  # Needed by //tools:download_file.py.
    'third_party/*.BUILD',  # Implicit dependencies of WORKSPACE file.
    'third_party/py/tensorflow/BUILD.in',  # Needed by ./configure
    'tools/workspace_status.sh',  # Needed by .bazelrc
    # tools/requirements.txt is always needed, but is handled separately.
]

# A list of relative paths to files which are excluded from export. Glob
# patterns are NOT supported.
EXCLUDED_FILES = [
    'config.pbtxt',  # Generated by ./configure
    'third_party/py/tensorflow/BUILD',  # Generated by ./configure
]


def BazelQuery(args: typing.List[str], timeout_seconds: int = 360, **kwargs):
  """Run bazel query with the specified args."""
  return subprocess.Popen(
      ['timeout', '-s9',
       str(timeout_seconds), 'bazel', 'query'] + args, **kwargs)


def MaybeTargetToPath(fully_qualified_target: str, source_root: pathlib.Path
                     ) -> typing.Optional[pathlib.Path]:
  """Determine if a bazel target refers to a file, and if so return the path."""

  def PathIfFile(path: str) -> typing.Optional[pathlib.Path]:
    """Return if given relative path is a file."""
    path = source_root / path
    return path if path.is_file() else None

  if fully_qualified_target.startswith('//:'):
    return PathIfFile(fully_qualified_target[3:])
  elif fully_qualified_target.startswith('//'):
    return PathIfFile(fully_qualified_target[2:].replace(':', '/'))
  else:
    raise TypeError('Target is not fully qualified (does not begin with `//`): '
                    f'{fully_qualified_target}')


def GetDependentFilesOrDie(
    target: str, source_root: pathlib.Path) -> typing.List[pathlib.Path]:
  """Get the file dependencies of the target or die."""
  with fs.chdir(source_root):
    bazel = BazelQuery([f'deps({target})'], stdout=subprocess.PIPE)
    grep = subprocess.Popen(['grep', '^/'],
                            stdout=subprocess.PIPE,
                            stdin=bazel.stdout,
                            universal_newlines=True)

  stdout, _ = grep.communicate()
  assert not bazel.returncode
  assert not grep.returncode

  targets = stdout.rstrip().split('\n')
  paths = [MaybeTargetToPath(target, source_root) for target in targets]
  return [p for p in paths if p]


def GetBuildFilesOrDie(target: str,
                       repo_root: pathlib.Path) -> typing.List[pathlib.Path]:
  """Get the BUILD files required for the given target."""
  with fs.chdir(repo_root):
    bazel = BazelQuery([f'buildfiles(deps({target}))'], stdout=subprocess.PIPE)
    cut = subprocess.Popen(['cut', '-f1', '-d:'],
                           stdout=subprocess.PIPE,
                           stdin=bazel.stdout)
    grep = subprocess.Popen(['grep', '^/'],
                            stdout=subprocess.PIPE,
                            stdin=cut.stdout,
                            universal_newlines=True)

  stdout, _ = grep.communicate()
  assert not bazel.returncode
  assert not cut.returncode
  assert not grep.returncode

  for line in stdout.rstrip().split('\n'):
    if line == '//external':
      continue
    path = repo_root / line[2:] / 'BUILD'
    if not path.is_file():
      raise OSError(f'BUILD file not found: {path}')
    yield path


def GetAlwaysExportedFilesOrDie(
    repo_root: pathlib.Path) -> typing.Iterable[pathlib.Path]:
  """Get hardcoded additional files to export."""
  paths = []
  for p in ALWAYS_INCLUDED_FILES:
    files = glob.glob(f'{repo_root}/{p}')
    assert files
    paths += [pathlib.Path(repo_root, p) for p in files]
  return paths


def GetAuxiliaryExportFiles(paths: typing.List[pathlib.Path]):
  """Get a list of auxiliary files to export."""

  def GlobToPaths(glob_pattern: str) -> typing.List[pathlib.Path]:
    return [pathlib.Path(p) for p in glob.glob(glob_pattern)]

  auxiliary_exports = []
  for path in paths:
    auxiliary_exports += GlobToPaths(f'{path.parent}/DEPS.txt')
    auxiliary_exports += GlobToPaths(f'{path.parent}/README*')
    auxiliary_exports += GlobToPaths(f'{path.parent}/LICENSE*')

  return paths + auxiliary_exports


def FilterExcludedPaths(
    paths: typing.List[pathlib.Path],
    repo_root: pathlib.Path) -> typing.Iterable[pathlib.Path]:
  for path in paths:
    relpath = os.path.relpath(path, repo_root)
    if relpath not in EXCLUDED_FILES:
      yield path


def GetAllSourceTreeFilesOrDie(
    target: str, repo_root: pathlib.Path) -> typing.List[pathlib.Path]:
  """Get the full list of source files to export for a target."""
  paths = list(GetDependentFilesOrDie(target, repo_root))
  paths += list(GetBuildFilesOrDie(target, repo_root))
  paths += list(GetAlwaysExportedFilesOrDie(repo_root))
  paths += list(GetAuxiliaryExportFiles(paths))
  return list(sorted(set(FilterExcludedPaths(paths, repo_root))))


def GetPythonRequirementsForTargetOrDie(
    targets: typing.List[str], source_root: pathlib.Path) -> typing.List[str]:
  """Get the subset of requirements.txt which is needed for a target."""
  # The set of bazel dependencies for all targets.
  dependencies = set()
  with fs.chdir(source_root):
    for target in targets:
      bazel = BazelQuery([f'deps({target})'], stdout=subprocess.PIPE)
      grep = subprocess.Popen(['grep', '^@pypi__'],
                              stdout=subprocess.PIPE,
                              stdin=bazel.stdout,
                              universal_newlines=True)

    stdout, _ = grep.communicate()
    assert not bazel.returncode
    output = stdout.rstrip()
    if output:
      dependencies = dependencies.union(set(output.split('\n')))

  with open(source_root / 'tools/requirements.txt') as f:
    all_requirements = set(f.readlines())

  needed = []
  for dependency in dependencies:
    # This is a pretty hacky approach that tries to match the package component
    # of the generated @pypi__<package>_<vesion> package to the name as it
    # appears in tools/requirements.txt.
    m = re.match(r'^@pypi__([^_]+)_', dependency)
    assert m.group(1)
    for r in all_requirements:
      if r.lower().startswith(m.group(1).lower()):
        needed.append(r)

  return list(sorted(set(needed)))


def ExportTargetsOrDie(source: pathlib.Path, destination: pathlib.Path,
                       targets: typing.List[str]):
  """Export the source tree of the given target to the destination directory."""
  destination.mkdir(parents=True, exist_ok=True)

  # Accumulate the set of all files for all targets.
  src_files = set()
  for target in targets:
    src_files = src_files.union(set(GetAllSourceTreeFilesOrDie(target, source)))

  # Copy each source tree file to its relative location in the destination tree.
  for path in sorted(src_files):
    relpath = os.path.relpath(path, source)
    dst = destination / relpath
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(relpath)
    shutil.copy(path, dst)

  # Export the subset of python requirements that are needed.
  print('tools/requirements.txt')
  requirements = GetPythonRequirementsForTargetOrDie(targets, source)
  requirements = sorted(set(requirements))
  with open(destination / 'tools/requirements.txt', 'w') as f:
    for r in requirements:
      f.write(f'{r}')


def CreateBazelWrapperForExports(destination: pathlib.Path,
                                 exported_targets: typing.List[str]) -> None:
  """Create a 'bazel_wrapper.py' script in the root of the destination tree.

  The bazel_wrapper.py script checks that any targets passed to bazel were part
  of the original export set.
  """
  print('bazel_wrapper.py')
  aux_targets = []
  for target in exported_targets:
    if ':' not in target:
      package_name = target.split('/')[-1]
      aux_targets.append(f'{target}:{package_name}')
  exported_targets += aux_targets

  targets_str = ',\n  '.join([f"'{x}'" for x in sorted(exported_targets)])
  with open(BAZEL_WRAPPER) as f:
    wrapper = f.read()
  wrapper = wrapper.replace('# @EXPORTED_TARGETS@ #', targets_str)
  with open(destination / 'bazel_wrapper.py', 'w') as f:
    f.write(wrapper)
  st = os.stat(destination / 'bazel_wrapper.py')
  os.chmod(destination / 'bazel_wrapper.py', st.st_mode | stat.S_IEXEC)


def UpdateReadme(destination: pathlib.Path,
                 exported_targets: typing.List[str]) -> None:
  """Prepend a header to the README.md with details."""
  phd_repo = git.Repo(path=getconfig.GetGlobalConfig().paths.repo_root)
  parent_hash = phd_repo.head.object.hexsha
  with open(destination / 'README.md') as f:
    readme = f.read()

  targets_str = '\n  '.join(
      [f'./bazel_wrapper.py build {x}' for x in exported_targets])
  readme = f"""# Subtree export from [phd](https://github.com/ChrisCummins/phd)

This repository was automatically generated by
[//tools/source_tree:export_source_tree](https://github.com/ChrisCummins/phd/blob/master/tools/source_tree/export_source_tree.py)
at {datetime.datetime.now()} from
[{parent_hash}](https://github.com/ChrisCummins/phd/commit/{parent_hash}).
It contains only the dependencies required for the following bazel targets:

```
  {targets_str}
```

To report issues, contribute patches, or use other targets,
please use the [parent repository](https://github.com/ChrisCummins/phd).

Begin original README:

""" + readme

  with open(destination / 'README.md', 'w') as f:
    f.write(readme)


def CopyFilesToDestinationOrDie(source: pathlib.Path, destination: pathlib.Path,
                                files_to_copy: typing.List[str]) -> None:
  for file_to_copy in files_to_copy:
    # File paths can be mappings from source to destination, using the form:
    #   <src>:<dst>.
    if len(file_to_copy.split(':')) == 2:
      src_relpath, dst_relpath = file_to_copy.split(':')
    else:
      src_relpath, dst_relpath = file_to_copy, file_to_copy

    src_path = source / src_relpath
    dst_path = destination / dst_relpath

    if not src_path.is_file():
      app.FatalWithoutStackTrace("File `%s` not found", file_to_copy)

    dst_path.parent.mkdir(exist_ok=True, parents=True)
    print(dst_relpath)
    shutil.copy(src_path, dst_path)


@contextlib.contextmanager
def DestinationDirectoryFromFlags() -> pathlib.Path:
  """Get the export destination."""
  if FLAGS.github_repo:
    with tempfile.TemporaryDirectory(prefix='phd_tools_source_tree_') as d:
      yield pathlib.Path(d)
  else:
    yield pathlib.Path(FLAGS.destination)


def GetOrCreateRepoOrDie(github: github_lib.Github) -> github_lib.Repository:
  """Get the github repository to export to. Create it if it doesn't exist."""
  repo_name = FLAGS.github_repo
  try:
    return github.get_user().get_repo(repo_name)
  except github_lib.UnknownObjectException as e:
    assert e.status == 404
    app.Log(1, "Creating repo %s", repo_name)
    github.get_user().create_repo(
        repo_name,
        description='PhD repo subtree export',
        homepage='https://github.com/ChrisCummins/phd',
        has_wiki=False,
        has_issues=False,
        private=FLAGS.github_repo_create_private)
    return GetOrCreateRepoOrDie(github)


def ExportToDirectoryOrDie(destination: pathlib.Path,
                           exported_targets: typing.List[str],
                           extra_files: typing.List[str]) -> None:
  """Export the requested targets to the destination directory."""
  source = pathlib.Path(getconfig.GetGlobalConfig().paths.repo_root)

  ExportTargetsOrDie(source, destination, FLAGS.targets)

  CreateBazelWrapperForExports(destination, exported_targets)
  UpdateReadme(destination, exported_targets)
  # Copy the extra files last so that we can trample over the generated README
  # file if required.
  CopyFilesToDestinationOrDie(source, destination, extra_files)


def CheckCallOrDie(cmd: typing.List[str]) -> None:
  """Run the given command and exit fatally on error."""
  try:
    subprocess.check_call(['git', 'add', '.'])
  except subprocess.CalledProcessError as e:
    app.FatalWithoutStackTrace("Command: `%s` failed with error: %s",
                               ' '.join(cmd), e)


def CloneRepoToDestinationOrDie(repo: github_lib.Repository,
                                destination: pathlib.Path):
  """Clone repo from github."""
  app.Log(1, 'Cloning from %s', repo.ssh_url)
  CheckCallOrDie(['git', 'clone', repo.ssh_url, str(destination)])
  # Delete everything except the .git directory. This is to enable files to be
  # removed between commits, as otherwise incremental commits would only ever
  # be additive.
  for path in list(destination.iterdir()):
    if path.exists() and path != (destination / '.git'):
      fs.rm(path)
  assert (destination / '.git').is_dir()


def CommitAndPushOrDie(local: pathlib.Path, remote: github_lib.Repository):
  """Create a commit, a tag, and push both to the remote repo."""
  phd_repo = git.Repo(path=getconfig.GetGlobalConfig().paths.repo_root)
  parent_hash = phd_repo.head.object.hexsha

  tag_name = datetime.datetime.now().strftime("%y%m%dT%H%M%S")
  app.Log(1, "Creating tag %s", tag_name)
  with fs.chdir(local):
    CheckCallOrDie(['git', 'add', '.'])
    CheckCallOrDie(
        ['git', 'commit', '-m', f'Subtree export from {parent_hash}'])
    CheckCallOrDie([
        'git', 'tag', '-a', tag_name, '-m', f'Subtree export from {parent_hash}'
    ])
    CheckCallOrDie(['git', 'push', 'origin', 'master'])
    CheckCallOrDie(['git', 'push', 'origin', tag_name])
  app.Log(1, 'Exported to %s', remote.html_url)


def main(argv: typing.List[str]):
  """Main entry point."""
  if len(argv) > 1:
    raise app.UsageError("Unknown arguments: '{}'.".format(' '.join(argv[1:])))

  # Get the list of targets to export.
  if not FLAGS.targets:
    raise app.UsageError('--target must be a bazel target(s)')
  targets = list(sorted(set(FLAGS.targets)))

  if not FLAGS.destination:
    raise app.UsageError('--destination must be a directory to create')

  extra_files = list(sorted(set(FLAGS.extra_files)))

  with DestinationDirectoryFromFlags() as destination:

    if FLAGS.github_repo:
      github = api.GetGithubConectionFromFlagsOrDie()
      repo = GetOrCreateRepoOrDie(github)
      CloneRepoToDestinationOrDie(repo, destination)
      ExportToDirectoryOrDie(destination, targets, extra_files)
      CommitAndPushOrDie(destination, repo)
    else:
      ExportToDirectoryOrDie(destination, targets, extra_files)
      app.Log(1, 'Exported subtree to %s', destination)


if __name__ == '__main__':
  app.RunWithArgs(main)
