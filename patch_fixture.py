import sys
content = sys.stdin.read()
new_content = content.replace(
    '    async def call(self, tool, arguments):\n        self.calls.append((tool, arguments))',
    '    async def call(self, tool, arguments):\n        if tool != "list_windows":\n            self.calls.append((tool, arguments))'
)
with open("python/native_fixture.py", "w") as f:
    f.write(new_content)
