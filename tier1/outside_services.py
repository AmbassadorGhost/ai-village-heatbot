"""Exploratory, conservative outside-service targets from executed tool inputs.

A target in an executed command is an inferred attempt, not proof of completed
network contact. Never scan agent speech, output, comments or arbitrary strings
for destinations. Preserve the frozen H1 classifier in its original file.
"""
import ast
import hashlib
import ipaddress
import re
import shlex
import warnings
from urllib.parse import urlsplit

VERSION = 'outside-service-target-v0.1'
NETWORK_PROGRAMS = {'curl', 'wget', 'http', 'https', 'httpie', 'git', 'ssh', 'scp', 'sftp', 'rsync'}
OPAQUE_NETWORK_PROGRAMS = {'pip', 'pip3', 'npm', 'npx', 'yarn', 'uv', 'apt', 'apt-get', 'docker', 'gh'}
PYTHON_PROGRAMS = {'python', 'python3', 'python3.11', 'python3.12'}
SKIP_VALUE = {'-d', '--data', '--data-raw', '--data-binary', '--data-urlencode',
              '-F', '--form', '-H', '--header', '-A', '--user-agent', '-u', '--user',
              '-o', '--output', '-T', '--upload-file', '-X', '--request',
              '--proxy', '-x', '--resolve', '--connect-to', '--cookie', '-b',
              '--cookie-jar', '-c', '--referer', '-e', '--max-time', '-m',
              '--connect-timeout', '--retry', '--retry-delay', '--cert', '--key',
              '--cacert', '--request-target', '-P', '--directory-prefix',
              '--post-data', '--post-file', '--input-file'}

def hostname(value):
    """Host only; discard user info, paths, queries, ports and fragments."""
    if not isinstance(value, str) or any(x in value for x in ('$(', '${', '`')):
        return None
    value = value.strip()
    try:
        if '://' in value:
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {'http', 'https', 'ftp', 'ftps', 'ws', 'wss', 'ssh', 'git'}:
                return None
            host = parsed.hostname
        else:
            # Accept explicit domain targets and user@host[:path] SSH syntax.
            host = value.split('@')[-1].split('/')[0].split(':')[0]
        if not host:
            return None
        host = host.lower().rstrip('.').encode('idna').decode('ascii')
        if host in {'localhost', 'localhost.localdomain'} or host.endswith(('.local', '.localhost', '.internal')):
            return None
        try:
            address = ipaddress.ip_address(host)
            return host if address.is_global else None
        except ValueError:
            pass
        if len(host) > 253 or '.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host):
            return None
        if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in host.split('.')):
            return None
        return host
    except (ValueError, UnicodeError):
        return None

def _python_targets(source):
    """Static literal HTTP calls; comments/docstrings alone cannot create targets."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return [], True
    aliases, values, targets = {}, {}, []
    def name(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return name(node.value) + '.' + node.attr
        return ''
    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return values.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = literal(node.left), literal(node.right)
            return left + right if left is not None and right is not None else None
        return None
    unresolved = False
    def visit(node):
        nonlocal unresolved
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            # A function definition is not evidence that its body ran.
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
            return
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = node.module + '.' + alias.name
            return
        if isinstance(node, ast.Assign):
            visit(node.value)
            value = literal(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values.pop(target.id, None)
                    if value is not None: values[target.id] = value
            return
        if isinstance(node, ast.Call):
            called = name(node.func)
            known = bool(re.fullmatch(r'(?:requests|httpx)\.(?:get|post|put|patch|delete|head|options|request)', called)) or called == 'urllib.request.urlopen'
            if known:
                position = 1 if called.endswith('.request') else 0
                argument = node.args[position] if len(node.args) > position else None
                argument = next((kw.value for kw in node.keywords if kw.arg == 'url'), argument)
                target = hostname(literal(argument)) if argument is not None else None
                if target:
                    targets.append((target, called))
                else:
                    unresolved = True
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Constant) and isinstance(node.test.value, bool):
                for child in (node.body if node.test.value else node.orelse): visit(child)
            else:
                # Conditional targets cannot be established without executing code.
                unresolved = True
                values.clear()
            return
        for child in ast.iter_child_nodes(node):
            visit(child)
    visit(tree)
    return targets, unresolved

def extract(command, _depth=0):
    if not isinstance(command, str) or _depth > 3:
        return {'outside_services': [], 'network_tools': [], 'target_status': 'unsupported_command', 'evidence': []}
    evidence, tools, unresolved = [], set(), False
    def add(host, tool, kind):
        if host:
            evidence.append({'hostname': host, 'tool': tool, 'basis': kind})
            tools.add(tool)
    # Heredoc bodies are data unless an interpreter explicitly executes them.
    lines = command.splitlines()
    shell_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if match and not line.lstrip().startswith('#'):
            delimiter = match.group(1)
            body = []
            i += 1
            while i < len(lines) and lines[i].strip() != delimiter:
                body.append(lines[i]); i += 1
            try:
                words = shlex.split(line, comments=True)
            except ValueError:
                words = []
            program = words[0].split('/')[-1] if words else ''
            if program in PYTHON_PROGRAMS:
                found, missing = _python_targets('\n'.join(body)); unresolved |= missing
                for host, tool in found:
                    add(host, tool, 'literal_http_call_in_executed_python_input')
            elif program in {'bash', 'sh'}:
                nested = extract('\n'.join(body), _depth+1)
                evidence.extend(nested['evidence']); tools.update(nested['network_tools'])
                unresolved |= nested['target_status'] in {'unresolved_or_opaque', 'partially_resolved'}
            elif program not in {'cat', 'tee', 'printf', 'echo'}:
                unresolved = True
            shell_lines.append(line[:match.start()])
        else:
            shell_lines.append(line)
        i += 1
    source = '\n'.join(shell_lines).replace('\\\n', ' ')
    # Keep newline as a command delimiter; shlex strips unquoted shell comments.
    for line in source.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=';&|()<>')
            lex.whitespace_split = True
            tokens = list(lex)
        except ValueError:
            unresolved = True; continue
        segments, segment = [], []
        for token in tokens:
            if token and set(token) <= set(';&|()'):
                if segment: segments.append(segment)
                segment = []
            else:
                segment.append(token)
        if segment: segments.append(segment)
        for words in segments:
            while words and (re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', words[0]) or words[0] in {'sudo', 'env', 'command', 'exec'}):
                words = words[1:]
            if not words: continue
            program = words[0].split('/')[-1]
            args = words[1:]
            if program in {'bash', 'sh'} and '-c' in args:
                idx = args.index('-c')
                if len(args) > idx + 1:
                    nested = extract(args[idx+1], _depth+1)
                    evidence.extend(nested['evidence']); tools.update(nested['network_tools'])
                    unresolved |= nested['target_status'] in {'unresolved_or_opaque', 'partially_resolved'}
                continue
            if program in PYTHON_PROGRAMS:
                if '-c' in args and len(args) > args.index('-c')+1:
                    found, missing = _python_targets(args[args.index('-c')+1]); unresolved |= missing
                    for host, tool in found: add(host, tool, 'literal_http_call_in_executed_python_input')
                elif args and not any(arg.startswith('<<') for arg in args) and args != ['-']:
                    unresolved = True  # Imported/local script effects are not visible here.
                continue
            if program in OPAQUE_NETWORK_PROGRAMS:
                unresolved = True
                continue
            if program not in NETWORK_PROGRAMS:
                continue
            if program == 'git' and not any(arg in {'clone', 'fetch', 'pull', 'push', 'ls-remote'} for arg in args):
                continue  # git config / remote add do not establish a contact attempt.
            tools.add(program)
            found = False
            skip = False
            ssh_target_seen = False
            for arg in args:
                if skip: skip = False; continue
                if arg in {'>', '>>', '<', '2>', '2>>', '&>'}: skip = True; continue
                if arg == '--url': continue
                if arg.startswith('--url='): arg = arg.split('=', 1)[1]
                elif program == 'wget' and arg in {'-O', '-i'}: skip = True; continue
                elif program in {'ssh', 'scp', 'sftp'} and arg in {'-i', '-p', '-P', '-l', '-J', '-F', '-o', '-L', '-R', '-D', '-S'}: skip = True; continue
                elif arg in SKIP_VALUE: skip = True; continue
                elif arg.startswith('-'): continue
                if program in {'ssh', 'sftp'}:
                    if ssh_target_seen: continue
                    ssh_target_seen = True
                if program in {'scp', 'rsync'} and '://' not in arg and not re.match(r'(?:[^@\s]+@)?[^/:\s]+:', arg):
                    continue  # A local filename with a dot is not a hostname.
                if program == 'git' and '://' not in arg and not re.match(r'[^@\s]+@[^:]+:', arg):
                    continue
                if program in {'curl', 'wget', 'http', 'https', 'httpie'} and '://' not in arg:
                    # curl supports bare domains, but only accept clear host/path.
                    if not re.match(r'^[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?:/|$)', arg): continue
                host = hostname(arg)
                if host:
                    add(host, program, 'explicit_network_tool_argument'); found = True
            unresolved |= not found
    unique = {tuple(sorted(item.items())): item for item in evidence}
    evidence = list(unique.values())
    hosts = sorted({item['hostname'] for item in evidence})
    status = ('partially_resolved' if unresolved else 'explicit_target_found') if hosts else ('unresolved_or_opaque' if unresolved else 'no_explicit_target_observed')
    return {'outside_services': hosts, 'network_tools': sorted(tools), 'target_status': status,
            'evidence': sorted(evidence, key=lambda item:(item['hostname'],item['tool'],item['basis']))}

def command_fingerprint(command):
    return hashlib.sha256(str(command).encode('utf-8')).hexdigest()

