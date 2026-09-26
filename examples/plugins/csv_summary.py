"""Example of an explicitly trusted local tool, not a sandboxed plugin."""
import csv
import io
from collections import Counter
from lebotclaw_harness import Tool


def summarize(args, context):
    path = context.path(args['path'])
    if path.stat().st_size > 1_000_000:
        raise ValueError('示例工具最多读取 1 MB CSV。')
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
    column = args['column']
    if not rows or column not in rows[0]:
        raise ValueError('CSV 为空或没有这个列名。')
    counts = Counter(row[column] for row in rows)
    return {'rows': len(rows), 'column': column, 'top_values': counts.most_common(20),
            'unique_values': len(counts)}


def register(registry):
    registry.register(Tool(
        name='csv_summary',
        description='统计项目内 CSV 指定列的取值分布，最多返回前 20 项。',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string'}, 'column': {'type': 'string'}},
            'required': ['path', 'column'], 'additionalProperties': False},
        handler=summarize,
        effect='read',
    ))
