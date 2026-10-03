import sys
content = sys.stdin.read()
new_content = content.replace(
    '        self.assertIsNone(select_window([dict(window_id=1, title="A"),\n                                         dict(window_id=2, title="", is_on_screen=True)], 7))',
    '        self.assertEqual(select_window([dict(window_id=1, title="A"),\n                                         dict(window_id=2, title="", is_on_screen=True)], 7), 1)'
)
with open("python/tests/test_native_repairs.py", "w") as f:
    f.write(new_content)
