# Configuration file for the Sphinx documentation builder.

project = 'AIQO PG AI Report'
author = 'AIQO Team'
release = '1.0'

extensions = [
    'sphinxcontrib.mermaid',
]

templates_path = ['_templates']
exclude_patterns = []

language = 'it'

html_theme = 'alabaster'
html_static_path = ['_static']

# Mermaid configuration
mermaid_version = "10.9.0"
