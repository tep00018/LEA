# security_audit.py
import os
import re
from pathlib import Path

def check_hardcoded_secrets(directory='.'):
    """Scan codebase for potential hardcoded secrets"""
    
    patterns = {
        'OpenAI API Key': r'sk-[a-zA-Z0-9]{48}',
        'Generic API Key': r'api[_-]?key[\s]*=[\s]*["\']([^"\']+)["\']',
        'Password': r'password[\s]*=[\s]*["\']([^"\']+)["\']',
        'Secret': r'secret[\s]*=[\s]*["\']([^"\']+)["\']',
        'Token': r'token[\s]*=[\s]*["\']([^"\']+)["\']',
        'Redis Password': r'redis[_-]?password[\s]*=[\s]*["\']([^"\']+)["\']',
        'Connection String': r'redis://[^@]+@[^\s]+',
        'ngrok Token': r'ngrok[_-]?token[\s]*=[\s]*["\']([^"\']+)["\']',
    }
    
    exclude_patterns = [
        r'\.git',
        r'__pycache__',
        r'\.pyc$',
        r'node_modules',
        r'\.egg-info',
        r'chroma_data',
        r'\.ipynb_checkpoints',
    ]
    
    findings = []
    
    for root, dirs, files in os.walk(directory):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not any(re.search(pat, d) for pat in exclude_patterns)]
        
        # Skip if current directory matches exclusion
        if any(re.search(pat, root) for pat in exclude_patterns):
            continue
            
        for file in files:
            # Only check code files
            if not file.endswith(('.py', '.yaml', '.yml', '.json', '.env', '.txt', '.sh', '.md')):
                continue
                
            filepath = Path(root) / file
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                for secret_type, pattern in patterns.items():
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Get line number
                        line_num = content[:match.start()].count('\n') + 1
                        findings.append({
                            'file': str(filepath),
                            'line': line_num,
                            'type': secret_type,
                            'match': match.group(0)[:50] + '...' if len(match.group(0)) > 50 else match.group(0)
                        })
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
    
    return findings

if __name__ == "__main__":
    print("🔍 Scanning for hardcoded credentials...\n")
    findings = check_hardcoded_secrets()
    
    if findings:
        print(f"⚠️  Found {len(findings)} potential issues:\n")
        for finding in findings:
            print(f"File: {finding['file']}")
            print(f"  Line {finding['line']}: {finding['type']}")
            print(f"  Match: {finding['match']}")
            print()
    else:
        print("✅ No obvious hardcoded credentials found!")