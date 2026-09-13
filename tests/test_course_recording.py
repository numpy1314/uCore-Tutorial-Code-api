"""Install on main once, then exercise recording on the real chapter branches."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_DIRS = ('.ai/agent-sessions', '.ai/events', '.ai/submissions')
sys.path.insert(0, str(ROOT / 'scripts'))
import course_runtime
from course_profile import load_profile

PROFILE = load_profile(ROOT)
PLUGIN_PATH = Path('plugins') / PROFILE['plugin_name']


def node_binary():
    if shutil.which('node'):
        return shutil.which('node')
    return next((str(path) for path in (Path.home() / '.vscode-server/bin').glob('*/node') if path.is_file()), None)


class CourseRecordingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=PROFILE['project'] + '-course-test-')
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.root = self.temp / 'project with spaces'
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(self.temp / 'gitconfig'),
                        GIT_CONFIG_NOSYSTEM='1', PYTHONDONTWRITEBYTECODE='1',
                        CODEX_HOME=str(self.temp / 'codex'), COURSE_TEST_LOG=str(self.temp / 'cli.jsonl'))
        self.run_command('git', 'clone', '--quiet', '--shared', '--no-checkout', str(ROOT), str(self.root), cwd=self.temp)
        self.git('switch', PROFILE['bootstrap_branch'])
        names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
        for name in filter(None, names):
            if any(name.startswith(directory + '/') for directory in RECORD_DIRS):
                continue
            path = ROOT / name
            if not path.is_file():
                continue
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        # Keep real classroom records out of the synthetic test fixture.
        for directory in RECORD_DIRS:
            if (self.root / directory).exists():
                shutil.rmtree(self.root / directory)
        self.git('config', 'user.name', 'Course Test')
        self.git('config', 'user.email', 'course-test@example.test')
        self.git('add', '.')
        self.git('commit', '--allow-empty', '-m', 'Course tools fixture')
        binary_dir = self.temp / 'bin'
        binary_dir.mkdir()
        fake = '''#!PYTHON
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['COURSE_TEST_LOG'], 'a') as log:
    log.write(json.dumps({'name': name, 'args': args})+'\\n')
if name == 'codex' and args and args[0] == 'exec':
    sys.stdin.read()
    messages = [
      {'type':'item.completed','item':{'id':'command','type':'command_execution','command':'git status','exit_code':0,'status':'completed'}},
      {'type':'item.completed','item':{'id':'change','type':'file_change','changes':[{'path':'os/main.c','kind':'update'}],'status':'completed'}},
      {'type':'item.completed','item':{'id':'reply','type':'agent_message','text':'COURSE_REPLY'}},
    ]
    for message in messages: print(json.dumps(message))
elif '--json' in args:
    print(json.dumps({'installed':[], 'marketplaces':[]} if name == 'codex' else []))
'''.replace('PYTHON', sys.executable)
        for name in ('code', 'cursor', 'codex', 'claude'):
            path = binary_dir / name
            path.write_text(fake)
            path.chmod(0o755)
        self.env['PATH'] = str(binary_dir) + os.pathsep + self.env['PATH']

    def run_command(self, *args, cwd=None, data=None, check=True, env=None):
        result = subprocess.run(args, cwd=cwd or self.root, env=env or self.env, input=data,
                                text=True, capture_output=True, timeout=30)
        if check:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def git(self, *args, **kwargs):
        return self.run_command('git', *args, **kwargs)

    def start_course(self, *args, script='course.py', **kwargs):
        # Exercise the real startup and shell installer without an endless log viewer.
        runner = '''import runpy, sys
scope = runpy.run_path(sys.argv[1])
scope['main'].__globals__['logs'] = lambda: None
sys.argv = sys.argv[1:]
scope['main']()
'''
        return self.run_command(sys.executable, '-c', runner, str(self.root / script), *args, **kwargs)

    def archive_agents(self, branch):
        runtime = self.root / course_runtime.RUNTIME_PATH / PLUGIN_PATH
        hooks = json.loads((runtime / 'hooks/hooks.json').read_text())['hooks']
        stamp = '2026-09-11T12:00:00Z'
        for agent in ('codex', 'claude-code'):
            source = self.temp / (branch + '-' + agent + '.jsonl')
            if agent == 'codex':
                records = [
                    {'timestamp': stamp, 'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': 'QUESTION_' + branch}},
                    {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'phase': 'final_answer', 'content': 'ANSWER_' + branch}},
                ]
            else:
                records = [
                    {'timestamp': stamp, 'type': 'user', 'message': {'role': 'user', 'content': 'QUESTION_' + branch}},
                    {'type': 'assistant', 'message': {'role': 'assistant', 'stop_reason': 'end_turn', 'content': 'ANSWER_' + branch}},
                ]
            source.write_text(''.join(json.dumps(record) + '\n' for record in records))
            env = {k:v for k,v in self.env.items() if k not in ('PLUGIN_ROOT','CLAUDE_PLUGIN_ROOT')}
            env['CLAUDE_PLUGIN_ROOT'] = str(runtime)
            if agent == 'codex':
                env['PLUGIN_ROOT'] = str(runtime)
            payload = {'hook_event_name':'Stop', 'cwd':str(self.root), 'session_id':branch,
                       'transcript_path':str(source), 'last_assistant_message':'ANSWER_' + branch}
            for event in ('Stop', 'SessionEnd'):
                payload['hook_event_name'] = event
                command = hooks[event][0]['hooks'][0]['command']
                self.run_command('bash', '-c', command, data=json.dumps(payload), env=env)
        cursor_hooks = json.loads((self.root / '.cursor/hooks.json').read_text())['hooks']
        for event, extra in (('beforeSubmitPrompt', {'prompt':'QUESTION_' + branch}),
                             ('afterAgentResponse', {'text':'ANSWER_' + branch})):
            payload = {'hook_event_name':event, 'conversation_id':branch, 'generation_id':'turn',
                       'workspace_roots':[str(self.root)], **extra}
            self.run_command('bash', '-c', cursor_hooks[event][0]['command'], data=json.dumps(payload))
        source = self.temp / (branch + '-copilot.jsonl')
        records = [
            ('session.start', {'sessionId':branch, 'version':1}),
            ('user.message', {'content':'QUESTION_' + branch}),
            ('assistant.turn_start', {'turnId':'0'}),
            ('assistant.message', {'content':'ANSWER_' + branch, 'toolRequests':[]}),
            ('assistant.turn_end', {'turnId':'0'}),
        ]
        source.write_text(''.join(json.dumps({'type':kind, 'data':data, 'id':str(i), 'timestamp':stamp})+'\n'
                                  for i,(kind,data) in enumerate(records)))
        hook = json.loads((self.root / '.github/hooks' / (PROFILE['plugin_name'] + '.json')).read_text())['hooks']['Stop'][0]
        self.run_command('bash', '-c', hook['command'], data=json.dumps({
            'hook_event_name':'Stop', 'session_id':branch, 'transcript_path':str(source),
            'cwd':str(self.root), 'timestamp':stamp}))
        for agent in ('codex', 'claude-code', 'cursor', 'vscode-copilot'):
            files = list((self.root / '.ai/agent-sessions' / agent).glob('*_' + branch + '.jsonl'))
            self.assertEqual(1, len(files), agent)
            content = files[0].read_text()
            self.assertIn('QUESTION_' + branch, content)
            self.assertIn('ANSWER_' + branch, content)
            self.assertEqual(0o600, files[0].stat().st_mode & 0o777)

    def record_paths(self):
        return sorted(str(path.relative_to(self.root)) for directory in RECORD_DIRS
                      for path in (self.root / directory).rglob('*') if path.is_file())

    def test_course_runtime_survives_all_course_lab_branches(self):
        node = node_binary()
        if not node:
            self.skipTest('Node.js is required to exercise the VSIX adapter')
        for branch in PROFILE['lab_branches']:
            ref = f'refs/heads/{branch}'
            if self.git('show-ref', '--verify', '--quiet', ref, cwd=ROOT, check=False).returncode:
                ref = f'refs/remotes/origin/{branch}'
            self.git('fetch', '--quiet', str(ROOT), f'{ref}:refs/heads/{branch}')
        # Normal installations create source-side bytecode that survives checkout.
        install_env = {key:value for key,value in self.env.items()
                       if key not in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}
        result = self.start_course(cwd=self.temp, env=install_env)
        self.assertIn('目标：auto', result.stdout)
        calls = [json.loads(line) for line in (self.temp / 'cli.jsonl').read_text().splitlines()]
        plugin_calls = [index for index, call in enumerate(calls)
                        if call['name'] in ('codex', 'claude') and call['args'][0] == 'plugin']
        extension_call = next(index for index, call in enumerate(calls)
                              if call['name'] == 'code' and call['args'][0] == '--install-extension')
        workspace_call = next(index for index, call in enumerate(calls)
                              if call['name'] == 'code' and call['args'][0] == '--new-window')
        self.assertTrue(plugin_calls)
        self.assertLess(max(plugin_calls), extension_call)
        self.assertLess(extension_call, workspace_call)
        self.assertTrue(list((self.root / 'scripts').rglob('*.pyc')))
        self.assertTrue(list((self.root / 'plugins').rglob('*.pyc')))
        self.assertEqual(course_runtime.HOOKS_PATH, self.git('config', '--get', 'core.hooksPath').stdout.strip())
        extension = self.temp / 'extension'
        with zipfile.ZipFile(self.root / '.ai/course-tools/.course-monitor/rewind-ide-0.3.1.vsix') as package:
            package.extractall(self.temp)
            self.assertEqual('0.3.1', json.loads(package.read('extension/package.json'))['version'])
        for branch in (PROFILE['bootstrap_branch'], *PROFILE['lab_branches']):
            with self.subTest(branch=branch):
                self.git('switch', branch)
                if branch != PROFILE['bootstrap_branch']:
                    self.assertFalse((self.root / 'course.py').exists())
                    self.assertFalse((self.root / PLUGIN_PATH / 'scripts/setup_agents.py').exists())
                    self.assertFalse((self.root / '.course-monitor/config.json').exists())
                    self.assertFalse((self.root / 'course-profile.json').exists())
                    for expected in PROFILE['lab_branches'][branch]:
                        self.assertTrue((self.root / expected).exists(), branch + ': ' + expected)
                    result = self.start_course('--agent', 'cursor', script='.ai/course-tools/course.py', cwd=self.root / 'os')
                    self.assertIn('目标：cursor', result.stdout)
                self.assertEqual(PROFILE, load_profile(self.root / course_runtime.RUNTIME_PATH))
                status = json.loads(self.git('course', 'status').stdout)
                self.assertTrue(status['recordingEnabled'])
                self.assertEqual(str(self.root), status['project'])
                self.run_command(node, str(ROOT / 'tests/record_vscode_events.cjs'), str(self.root), str(extension))
                self.git('course', 'codex', data='COURSE_PROMPT_' + branch)
                self.archive_agents(branch)
                # Ordinary staging includes raw records, but excludes installed tools and policies.
                records = self.record_paths()
                self.assertTrue(records)
                self.assertEqual(['?? ' + name for name in records],
                                 self.git('status', '--porcelain', '--untracked-files=all').stdout.splitlines())
                self.git('add', '.')
                self.assertEqual(records, self.git('diff', '--cached', '--name-only').stdout.splitlines())
                self.git('commit', '-m', 'Checkpoint ' + branch)
                paths = self.git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').stdout.splitlines()
                self.assertEqual(self.record_paths(), paths)
                for directory in RECORD_DIRS:
                    self.assertTrue(any(name.startswith(directory + '/') for name in paths), directory)
                submitted = [json.loads(line) for name in paths if name.startswith('.ai/submissions/')
                             for line in (self.root / name).read_text().splitlines()]
                events = [json.loads(line) for name in paths if name.startswith('.ai/events/')
                          for line in (self.root / name).read_text().splitlines()]
                self.assertEqual({event['id'] for event in events}, {event['id'] for event in submitted})
                self.assertIn('ai_prompt', {event['type'] for event in submitted})
                self.assertIn('file_save', {event['type'] for event in submitted})
                source = 'README.md' if branch == PROFILE['bootstrap_branch'] else 'os/main.c'
                self.assertTrue(any(event['type'] == 'file_save' and event.get('file') == source
                                    for event in submitted))
                self.assertTrue(any(event['type'] == 'ai_file_operation' and event.get('file') == 'os/main.c'
                                    for event in submitted))
                self.assertEqual(len(submitted), len({event['id'] for event in submitted}))
                self.assertEqual('', self.git('status', '--porcelain').stdout.strip())
                self.assertFalse((self.root / '.vscode/settings.json').exists())
        # Reconfigure from a chapter with no source tooling and preserve local choices.
        policy = self.root / '.cursor/session-archive.json'
        policy.write_text('{"enabled":false,"mode":"full"}')
        self.git('agent-plugins', 'cursor')
        self.assertEqual({'enabled':False, 'mode':'full'}, json.loads(policy.read_text()))
        self.git('agent-plugins', 'vscode')
        settings = self.root / '.vscode/settings.json'
        self.assertFalse(settings.exists())
        custom_settings = '{\n// Local C preferences\n"C_Cpp.default.cStandard": "c11"\n}\n'
        settings.write_text(custom_settings)
        self.git('agent-plugins', 'vscode')
        self.assertEqual(custom_settings, settings.read_text())
        self.assertEqual('', self.git('status', '--porcelain').stdout.strip())

    def test_start_selects_only_requested_agent_with_existing_options(self):
        result = self.start_course('start', '--agent', 'codex', '--skip-extension')
        self.assertIn('目标：codex', result.stdout)
        self.assertTrue((self.root / '.codex/session-archive.json').is_file())
        for directory in ('.claude', '.cursor', '.vscode'):
            self.assertFalse((self.root / directory / 'session-archive.json').exists())
        calls = [json.loads(line) for line in (self.temp / 'cli.jsonl').read_text().splitlines()]
        self.assertTrue(any(call['name'] == 'codex' and call['args'][0] == 'plugin' for call in calls))
        self.assertFalse(any(call['name'] == 'claude' for call in calls))
        self.assertFalse(any(call['args'][0] == '--install-extension' for call in calls))
        self.assertTrue(any(call['name'] == 'code' and call['args'][0] == '--new-window' for call in calls))

    def test_start_stops_before_recording_install_when_agent_setup_fails(self):
        policy = self.root / '.cursor/session-archive.json'
        policy.parent.mkdir(exist_ok=True)
        policy.write_text('{"enabled":')
        result = self.start_course(check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('配置未完成', result.stderr)
        self.assertEqual('{"enabled":', policy.read_text())
        self.assertFalse((self.root / '.ai/course-tools').exists())
        self.assertFalse((self.temp / 'cli.jsonl').exists())

    def test_alternate_course_identity_survives_branch_switch(self):
        branch = next(iter(PROFILE['lab_branches']))
        profile = dict(PROFILE, project='example', display_name='Example Course',
                       plugin_name='example-archive', marketplace_name='example-course',
                       lab_branches={branch: PROFILE['lab_branches'][branch]})
        (self.root / 'course-profile.json').write_text(json.dumps(profile))
        renamed = self.root / 'plugins' / profile['plugin_name']
        (self.root / PLUGIN_PATH).rename(renamed)
        for relative in ('.agents/plugins/marketplace.json', '.claude-plugin/marketplace.json'):
            path = self.root / relative
            data = json.loads(path.read_text())
            data['name'] = profile['marketplace_name']
            entry = data['plugins'][0]
            entry['name'] = profile['plugin_name']
            source = './plugins/' + profile['plugin_name']
            if isinstance(entry['source'], dict):
                entry['source']['path'] = source
            else:
                entry['source'] = source
            path.write_text(json.dumps(data))
        for relative in ('.codex-plugin/plugin.json', '.claude-plugin/plugin.json'):
            path = renamed / relative
            data = json.loads(path.read_text())
            data['name'] = profile['plugin_name']
            path.write_text(json.dumps(data))
        self.git('add', '.')
        self.git('commit', '-m', 'Alternate course identity fixture')
        self.run_command(sys.executable, 'course.py', 'install', '--skip-extension')
        result = self.run_command('bash', 'scripts/setup-agent-plugins.sh', 'all')
        self.assertIn('Example Course', result.stdout)
        calls = (self.temp / 'cli.jsonl').read_text()
        self.assertIn('example-archive@example-course', calls)
        self.assertNotIn(PROFILE['plugin_name'], calls)
        ref = f'refs/heads/{branch}'
        if self.git('show-ref', '--verify', '--quiet', ref, cwd=ROOT, check=False).returncode:
            ref = f'refs/remotes/origin/{branch}'
        self.git('fetch', '--quiet', str(ROOT), f'{ref}:refs/heads/{branch}')
        self.git('switch', branch)
        self.assertFalse((self.root / 'course-profile.json').exists())
        self.assertTrue(json.loads(self.git('course', 'status').stdout)['recordingEnabled'])
        for agent, directory in (('cursor', '.cursor'), ('vscode', '.vscode')):
            self.git('agent-plugins', agent)
            runtime = self.root / directory / 'example-hooks'
            self.assertEqual(profile, load_profile(runtime))
            script = 'cursor_hook.py' if agent == 'cursor' else 'copilot_hook.py'
            # Exercise the copied hook and loader with no source profile present.
            self.run_command(sys.executable, str(runtime / script), data='{}')
        hooks = json.loads((self.root / '.cursor/hooks.json').read_text())['hooks']
        payload = {'hook_event_name': 'beforeSubmitPrompt', 'conversation_id': 'example',
                   'generation_id': 'turn', 'workspace_roots': [str(self.root)],
                   'prompt': 'EXAMPLE_COURSE_PROMPT'}
        self.run_command('bash', '-c', hooks['beforeSubmitPrompt'][0]['command'], data=json.dumps(payload))
        archives = list((self.root / '.ai/agent-sessions/cursor').glob('*.jsonl'))
        self.assertTrue(any('EXAMPLE_COURSE_PROMPT' in path.read_text() for path in archives))
        self.assertTrue((self.root / '.github/hooks/example-archive.json').is_file())
        records = self.record_paths()
        self.assertTrue(records)
        self.assertEqual(['?? ' + name for name in records],
                         self.git('status', '--porcelain', '--untracked-files=all').stdout.splitlines())
        self.git('add', '.')
        self.assertEqual(records, self.git('diff', '--cached', '--name-only').stdout.splitlines())

    def test_missing_or_inconsistent_profile_fails_before_install(self):
        path = self.root / 'course-profile.json'
        path.unlink()
        result = self.run_command(sys.executable, 'course.py', 'install', '--skip-extension', check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.root / course_runtime.RUNTIME_PATH).exists())
        path.write_text(json.dumps(dict(PROFILE, marketplace_name='wrong-marketplace')))
        result = self.run_command(sys.executable, 'course.py', 'install', '--skip-extension', check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.root / course_runtime.RUNTIME_PATH).exists())
        self.assertEqual('', self.git('config', '--get', 'alias.course', check=False).stdout)

    def test_codex_session_reason_tracks_final_outcome(self):
        self.run_command(sys.executable, 'course.py', 'install', '--skip-extension')
        cases = (
            ([], 0, 0, 'completed'),
            ([{'type': 'error', 'message': 'retrying'}, {'type': 'turn.completed'}], 0, 0, 'completed_after_retry'),
            ([{'type': 'turn.failed'}, {'type': 'turn.completed'}], 0, 0, 'completed_after_retry'),
            ([{'type': 'turn.failed'}], 1, 1, 'codex_turn_failed'),
            ([{'type': 'turn.failed'}], 0, 1, 'codex_turn_failed'),
            ([{'type': 'error', 'message': 'unavailable'}], 2, 2, 'codex_process_failed'),
            ([], 3, 3, 'codex_process_failed'),
        )
        for messages, process_code, expected_code, reason in cases:
            with self.subTest(messages=messages, code=process_code):
                binary = self.temp / 'bin/codex'
                script = '#!' + sys.executable + '\nimport sys\nsys.stdin.read()\n'
                if messages:
                    script += 'print(' + repr('\n'.join(json.dumps(m) for m in messages)) + ')\n'
                script += 'sys.exit(' + str(process_code) + ')\n'
                binary.write_text(script)
                binary.chmod(0o755)
                events = self.root / '.ai/events'
                before = set(events.glob('*.jsonl'))
                result = self.git('course', 'codex', data='TEST_PROMPT', check=False)
                self.assertEqual(expected_code == 0, result.returncode == 0, result.stderr)
                journal, = set(events.glob('*.jsonl')) - before
                end = json.loads(journal.read_text().splitlines()[-1])
                self.assertEqual('session_end', end['type'])
                self.assertEqual(expected_code, end['exit_code'])
                self.assertEqual(reason, end['reason'])

    def test_reinstall_preserves_disabled_policy_logs_and_local_git_exclusions(self):
        self.run_command(sys.executable, 'course.py', 'install', '--skip-extension')
        config = self.root / '.ai/course-tools/.course-monitor/config.json'
        value = json.loads(config.read_text())
        value.update(enabled=False, custom='keep')
        config.write_text(json.dumps(value))
        for directory in RECORD_DIRS:
            journal = self.root / directory / 'keep.jsonl'
            journal.parent.mkdir(parents=True, exist_ok=True)
            journal.write_text('KEEP\n')
        exclude = self.root / '.git/info/exclude'
        with exclude.open('a') as output:
            output.write('/my-local-files/\n')
            for directory in RECORD_DIRS:
                output.write('/' + directory + '/\n')
        self.run_command(sys.executable, 'course.py', 'install', '--skip-extension')
        self.assertEqual(value, json.loads(config.read_text()))
        for directory in RECORD_DIRS:
            self.assertEqual('KEEP\n', (self.root / directory / 'keep.jsonl').read_text())
            self.assertNotIn('/' + directory + '/', exclude.read_text().splitlines())
        self.assertIn('/my-local-files/', exclude.read_text())
        self.assertEqual(1, exclude.read_text().splitlines().count('/.ai/course-tools/'))
        self.assertFalse(json.loads(self.git('course', 'status').stdout)['recordingEnabled'])
        self.git('add', '.')
        self.assertEqual(self.record_paths(), self.git('diff', '--cached', '--name-only').stdout.splitlines())
        before = exclude.read_bytes()
        self.run_command(sys.executable, 'course.py', 'install', '--skip-extension')
        self.assertEqual(before, exclude.read_bytes())

    def test_existing_commit_hook_is_preserved(self):
        hook = self.root / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 0\n')
        before = hook.read_bytes()
        result = self.run_command(sys.executable, 'course.py', 'install', '--skip-extension', check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, hook.read_bytes())
        self.assertFalse((self.root / '.ai/course-tools').exists())

    def test_symlink_runtime_is_rejected(self):
        outside = self.temp / 'outside'
        outside.mkdir()
        (self.root / '.ai').mkdir(exist_ok=True)
        (self.root / '.ai/course-tools').symlink_to(outside, target_is_directory=True)
        result = self.run_command(sys.executable, 'course.py', 'install', '--skip-extension', check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], list(outside.iterdir()))


if __name__ == '__main__':
    unittest.main()
