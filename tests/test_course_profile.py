"""Validate course contracts and static client manifests without installing tools."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from course_profile import load_profile, validate_distribution, validate_profile


class CourseProfileTests(unittest.TestCase):
    def test_distribution_matches_profile(self):
        validate_distribution(ROOT, load_profile(ROOT))

    def test_invalid_profiles_are_rejected(self):
        profile = load_profile(ROOT)
        for key, value in (
            ('schema_version', True), ('schema_version', 2),
            ('project', '../outside'), ('plugin_name', 'a/b'),
            ('marketplace_name', 'bad"name'), ('display_name', ''),
            ('bootstrap_branch', '-bad'), ('lab_branches', {}),
            ('lab_branches', {'main': ['os/main.c']}),
            ('lab_branches', {'ch3': ['../outside']}),
            ('lab_branches', {'ch3': ['/absolute']}),
            ('lab_branches', {'ch3': ['os/main.c', 'os/main.c']}),
            ('lab_branches', {'ch3': []}),
        ):
            with self.subTest(key=key, value=value):
                invalid = copy.deepcopy(profile)
                invalid[key] = value
                with self.assertRaises(ValueError):
                    validate_profile(invalid)

    def test_native_hook_profile_takes_precedence_over_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = load_profile(ROOT)
            (root / 'course-profile.json').write_text(json.dumps(profile))
            hook = root / '.cursor/example-hooks'
            hook.mkdir(parents=True)
            installed = dict(profile, project='example')
            (hook / 'course-profile.json').write_text(json.dumps(installed))
            self.assertEqual('example', load_profile(hook)['project'])


if __name__ == '__main__':
    unittest.main()
