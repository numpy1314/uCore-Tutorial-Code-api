"""Install branch-independent course tools in the local checkout."""

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from course_profile import load_profile, validate_distribution

RUNTIME_PATH = Path('.ai/course-tools')
HOOKS_PATH = '.ai/course-tools/.course-monitor/hooks'

def local_paths(profile):
    hooks = profile['project'] + '-hooks/'
    return (
        '.ai/course-tools/', '.ai/ide/',
        '.codex/config.toml', '.codex/session-archive.json',
        '.claude/settings.json', '.claude/settings.local.json', '.claude/session-archive.json',
        '.cursor/hooks.json', '.cursor/session-archive.json', '.cursor/' + hooks,
        '.vscode/session-archive.json', '.vscode/' + hooks,
        '.github/hooks/' + profile['plugin_name'] + '.json',
    )


def bundle_files(profile):
    return ('course.py', 'course-profile.json', '.course-monitor', 'plugins/' + profile['plugin_name'],
            'scripts', '.agents/plugins/marketplace.json', '.claude-plugin/marketplace.json')


def project_root(bundle):
    bundle = Path(bundle).resolve()
    if bundle.name == 'course-tools' and bundle.parent.name == '.ai':
        return bundle.parent.parent
    return bundle


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, encoding='utf-8').strip()


def ordinary_path(root, path):
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            raise ValueError('记录工具路径不能是符号链接：' + str(candidate))


def write_file(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install_runtime(bundle, root=None):
    """Copy only executable tooling; preserve the installed project policy."""
    bundle = Path(bundle).resolve()
    root = project_root(bundle) if root is None else Path(root).resolve()
    if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root:
        raise ValueError('请在实验仓库根目录安装记录工具。')
    profile = load_profile(bundle)
    validate_distribution(bundle, profile)
    setup_path = Path('plugins') / profile['plugin_name'] / 'scripts/setup_agents.py'
    runtime = root / RUNTIME_PATH
    ordinary_path(root, runtime)
    if bundle != runtime:
        copies = []
        for name in bundle_files(profile):
            source = bundle / name
            if not source.exists():
                raise ValueError('记录工具文件缺失，请从 ' + profile['bootstrap_branch'] + ' 分支安装：' + name)
            for path in sorted(source.rglob('*')) if source.is_dir() else [source]:
                if path.is_symlink():
                    raise ValueError('记录工具源文件不能是符号链接：' + str(path))
                if not path.is_file() or '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'} or path.is_relative_to(bundle / '.course-monitor/node'):
                    continue
                relative = path.relative_to(bundle)
                destination = runtime / relative
                ordinary_path(root, destination)
                if relative.as_posix() == '.course-monitor/config.json' and destination.exists():
                    continue
                copies.append((path, destination))
        for source, destination in copies:
            write_file(destination, source.read_bytes(), 0o700 if source.stat().st_mode & 0o111 else 0o600)
    if not (runtime / setup_path).is_file():
        raise ValueError('归档插件运行文件不完整，请从 ' + profile['bootstrap_branch'] + ' 分支重新安装。')
    exclude = Path(git(root, 'rev-parse', '--git-path', 'info/exclude'))
    if not exclude.is_absolute():
        exclude = root / exclude
    if exclude.is_symlink():
        raise ValueError('Git 本地排除配置不能是符号链接。')
    current = exclude.read_text(encoding='utf-8') if exclude.exists() else ''
    # Migrate older installs so existing course records can be submitted with code.
    record_patterns = {'/.ai/' + name + '/' for name in ('agent-sessions', 'events', 'submissions')}
    text = ''.join(line for line in current.splitlines(keepends=True)
                   if line.rstrip('\r\n') not in record_patterns)
    # Source-side caches remain after main's tracked Python files are checked out.
    # Keep these patterns unanchored so they cover caches at any directory depth.
    patterns = ['/' + name for name in local_paths(profile)] + ['__pycache__/', '*.py[cod]']
    missing = [pattern for pattern in patterns if pattern not in text.splitlines()]
    if missing:
        text += '\n' if text and not text.endswith('\n') else ''
        text += '# Installed course tools and local configuration survive branch switches.\n'
        text += '\n'.join(missing) + '\n'
    if text != current:
        write_file(exclude, text.encode('utf-8'))
    aliases = {
        'course': [sys.executable, str(RUNTIME_PATH / 'course.py')],
        'agent-plugins': [sys.executable, str(RUNTIME_PATH / setup_path)],
    }
    for name, command in aliases.items():
        git(root, 'config', '--local', 'alias.' + name, '!' + shlex.join(command))
    return runtime
