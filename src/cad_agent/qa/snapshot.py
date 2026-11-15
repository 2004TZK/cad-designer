"""DXF 语义快照：实体几何、图层/样式和非匿名块；忽略运行时 handle 引用。"""
from ezdxf.lldxf.tagwriter import TagCollector


def _value(v):
    if isinstance(v,float):
        return round(v,7)
    if isinstance(v,(str,int,bool)) or v is None:
        return v
    try:
        return [_value(x) for x in v]
    except TypeError:
        return str(v)


def entity_record(e, text=True):
    ignored = {5,105,330,360}
    if e.dxftype() == 'DIMENSION':
        ignored.add(2)  # 重新渲染的匿名块名称随保存变化。
    if not text and e.dxftype() in ('TEXT','MTEXT','DIMENSION','TOLERANCE'):
        ignored.update((1,3))
    return [[tag.code,_value(tag.value)] for tag in TagCollector.dxftags(e)
            if tag.code not in ignored]


def drawing_snapshot(doc, text=True):
    return {
        'version':doc.dxfversion,
        'entities':{e.dxf.handle:entity_record(e,text) for e in doc.modelspace()},
        'tables':{name:{e.dxf.name:entity_record(e) for e in getattr(doc,name)}
                  for name in ('layers','styles','dimstyles','linetypes')},
        'blocks':{b.name:[entity_record(e) for e in b] for b in doc.blocks if not b.name.startswith('*')},
    }


def snapshot_diff(before, after):
    changes = {}
    for section in ('entities','tables','blocks'):
        a,b = before.get(section,{}),after.get(section,{})
        delta = [key for key in sorted(set(a)|set(b)) if a.get(key) != b.get(key)]
        if delta:
            changes[section] = delta
    if before.get('version') != after.get('version'):
        changes['version'] = [before.get('version'),after.get('version')]
    return changes
