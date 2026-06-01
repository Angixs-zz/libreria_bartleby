import os
import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # The pattern should match the intermediate breadcrumb items.
    # The intermediate breadcrumb item is a span with text-muted followed by a chevron_right span.
    # We want to remove things like:
    # <span style="color: var(--text-muted);">Autenticación</span>
    # <span class="material-symbols-outlined text-sm" style="color: var(--border);">chevron_right</span>
    # It might be indented.
    
    # Let's match:
    # \s*<span[^>]*style="[^"]*color:\s*var\(--text-muted\)[^"]*"[^>]*>(?:(?!<span).)*?</span>\s*<span[^>]*>chevron_right</span>
    
    pattern = r'(\s*<span[^>]*style="[^"]*color:\s*var\(--text-muted\)[^"]*"[^>]*>(?:(?!<span).)*?</span>\s*<span[^>]*>chevron_right</span>)'
    
    # We only want to remove it if it's right before another chevron_right or the final span.
    # Wait, the current page breadcrumb uses var(--text), not var(--text-muted) in most templates!
    # Let's verify by looking at a template:
    # <span style="color: var(--text-muted);">Autenticación</span>
    # <span class="material-symbols-outlined text-sm" style="color: var(--border);">chevron_right</span>
    # <span style="color: var(--text);">Iniciar Sesión</span>
    
    # Sometimes it might be an 'a' tag. We ONLY want to remove SPAN tags with --text-muted that are NOT links, followed by a chevron_right.
    
    new_content = re.sub(pattern, '', content, flags=re.IGNORECASE)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'Fixed {filepath}')

for root, dirs, files in os.walk('.'):
    if 'venv' in root or '.git' in root or 'node_modules' in root:
        continue
    for file in files:
        if file.endswith('.html'):
            process_file(os.path.join(root, file))
