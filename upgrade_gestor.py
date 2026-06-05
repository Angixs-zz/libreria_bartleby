import os

html_path = r'c:\Users\migue\libreria_bartleby\reservas\templates\reservas\gestor_reservas.html'

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix the "cut off" green color by removing overflow-hidden from the main wrapper
content = content.replace(
    '<div class="flex-1 min-w-0 relative overflow-hidden">',
    '<div class="flex-1 min-w-0 relative">'
)

# Move the background blobs to have a better distribution and not look "cut off"
content = content.replace(
    '<!-- Decorative background blobs -->\n    <div class="absolute top-0 right-0 w-full max-w-3xl h-[500px] bg-[#d2eca2]/30 dark:bg-[#3e5219]/10 blur-[120px] rounded-full pointer-events-none transform translate-x-1/3 -translate-y-1/4"></div>\n    <div class="absolute top-[40vh] left-0 w-full max-w-2xl h-[400px] bg-blue-100/40 dark:bg-blue-900/10 blur-[100px] rounded-full pointer-events-none transform -translate-x-1/3"></div>',
    '<!-- Decorative background blobs -->\n    <div class="absolute -top-20 -right-20 w-[600px] h-[600px] bg-[#a3c46a]/20 dark:bg-[#3e5219]/20 blur-[100px] rounded-full pointer-events-none"></div>\n    <div class="absolute top-[30vh] -left-20 w-[500px] h-[500px] bg-blue-200/20 dark:bg-blue-900/20 blur-[100px] rounded-full pointer-events-none"></div>'
)

# 2. Improve the aesthetic of Stats Cards by adding backdrop blur and softer borders
content = content.replace(
    'bg-white dark:bg-[#1b1c1a] border border-gray-200 dark:border-gray-800 shadow-sm hover:shadow-md',
    'bg-white/80 dark:bg-[#1b1c1a]/80 backdrop-blur-xl border border-gray-200/50 dark:border-gray-800/50 shadow-sm hover:shadow-lg'
)

# Improve card border radius for stats
content = content.replace('rounded-xl p-8 group', 'rounded-3xl p-8 group')

# 3. Enhance the Reserva Cards (apartados en curso)
# Replace CSS for reserva-*
css_old = """    .reserva-verde {
        border-left: 4px solid #3e5219;
    }

    .reserva-amber {
        border-left: 4px solid #d97706;
    }

    .reserva-roja {
        border-left: 4px solid #ba1a1a;
    }"""
css_new = """    .reserva-verde {
        border-left: 6px solid #4A5D23;
    }

    .reserva-amber {
        border-left: 6px solid #d97706;
    }

    .reserva-roja {
        border-left: 6px solid #ba1a1a;
    }"""
content = content.replace(css_old, css_new)

# Upgrade the reserva card layout
content = content.replace(
    'class="reserva-card-item rounded-xl overflow-hidden transition-all hover:shadow-md bg-white dark:bg-[#1b1c1a] border border-gray-200 dark:border-gray-800 {% if h > 48 %}reserva-verde{% elif h > 24 %}reserva-amber{% else %}reserva-roja{% endif %}">',
    'class="reserva-card-item rounded-2xl overflow-hidden transition-all duration-300 hover:shadow-xl hover:-translate-y-1 bg-white/90 dark:bg-[#1b1c1a]/90 backdrop-blur-md border border-gray-100 dark:border-gray-800 {% if h > 48 %}reserva-verde{% elif h > 24 %}reserva-amber{% else %}reserva-roja{% endif %}">'
)

content = content.replace(
    '<div class="p-4 md:p-5 flex flex-col md:flex-row items-center gap-4 md:gap-6">',
    '<div class="p-5 md:p-6 flex flex-col md:flex-row items-center gap-5 md:gap-8">'
)

content = content.replace(
    '<div class="flex-grow w-full md:w-auto">',
    '<div class="flex-grow w-full md:w-auto bg-gray-50/50 dark:bg-white/5 rounded-xl p-3">'
)

# 4. Improve search input design
content = content.replace(
    'class="w-full pr-4 py-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#1b1c1a] text-[#1b1c1a] dark:text-white focus:ring-2 focus:ring-[#3e5219] dark:focus:ring-[#d2eca2] outline-none transition-all font-mono text-sm"',
    'class="w-full pr-4 py-3.5 rounded-2xl border border-gray-200/80 dark:border-gray-700/80 bg-white/80 dark:bg-[#1b1c1a]/80 backdrop-blur-md text-[#1b1c1a] dark:text-white focus:ring-2 focus:ring-[#3e5219] dark:focus:ring-[#d2eca2] outline-none transition-all shadow-sm font-mono text-sm"'
)

# 5. History tables rounded corners and backdrop
content = content.replace(
    'rounded-xl overflow-hidden bg-white dark:bg-[#1b1c1a] border border-gray-200 dark:border-gray-800',
    'rounded-3xl overflow-hidden bg-white/80 dark:bg-[#1b1c1a]/80 backdrop-blur-xl border border-gray-200/50 dark:border-gray-800/50 shadow-sm'
)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Aesthetics upgraded.")
