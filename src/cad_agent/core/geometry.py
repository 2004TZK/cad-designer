"""已实现的几何能力范围，以及多轴段长度变化的坐标映射。"""
from bisect import bisect_right
from ..qa.snapshot import entity_record


def unsupported_changes(data, assets):
    # 这些参数需要尚未实现的径向/键槽算子。不能只改文字冒充出图完成。
    fixed = {'gear': {'d2':268,'da2':272,'rim_inner':252,'hub_d':56,'bore_d':35,
                      'hub_l':54,'b2':54,'web_t':10,'key_w':10,'key_depth':39,'key_len':45},
             'shaft': {'key1_w':8,'key2_w':10,'key1_l':50,'key2_l':45,
                       'key1_depth':19.5,'key2_depth':31,'key1_pos':2,'key2_pos':3.5}}
    for i,seg in enumerate(assets['geo_groups']['shaft']['sketch']['segments'],1):
        fixed['shaft'][f'seg{i}_d'] = seg['r']*2
    pending=[]
    for part, fields in fixed.items():
        for key, old in fields.items():
            fid=part+'.'+key
            value=data[part].get(fid,{}).get('value')
            if value is not None and abs(float(value)-old)>1e-6:
                pending.append({'part':part,'id':fid,'item':key,'old':old,'value':value,
                                'reason':'该参数的几何算子尚未实现；不能仅替换标注'})
    for seg,key in ((1,1),(4,2)):
        table=data['shaft']
        length=table[f'shaft.seg{seg}_l']['value']
        required=table[f'shaft.key{key}_l']['value']+table[f'shaft.key{key}_pos']['value']
        if length<required:
            pending.append({'part':'shaft','id':f'shaft.seg{seg}_l','item':'键槽包容检查',
                            'value':length,'reason':f'当前槽长和定位要求该段长度至少 {required:g}'})
    return pending


def shift_shaft(doc, op):
    old,new=op['old_bounds'],op['new_bounds']
    deltas=[b-a for a,b in zip(old,new)]
    limit=op.get('follow_threshold',20)
    if max(abs(d) for d in deltas)>limit and not op.get('large_move_confirmed'):
        from ..mcp.editor import EditorError
        raise EditorError(f'G5 累计移动超过 {limit:g}，转 H4 确认')

    def xmap(x):
        for a,b in zip(old,new):
            if abs(x-a)<.2:
                return x+b-a
        index=max(0,min(bisect_right(old,x)-1,len(old)-1))
        return x+deltas[index]

    def point(p):
        return (xmap(p[0]),p[1],p[2] if len(p)>2 else 0)

    allowed=set(op.get('entities',[]))
    result=[]
    for e in doc.modelspace():
        if allowed and e.dxf.handle not in allowed:
            continue
        before=entity_record(e)
        kind=e.dxftype()
        if kind=='LINE':
            e.dxf.start=point(e.dxf.start)
            e.dxf.end=point(e.dxf.end)
        elif kind in ('ARC','CIRCLE'):
            e.dxf.center=point(e.dxf.center)
        elif kind=='LWPOLYLINE':
            e.set_points([(xmap(x),y,s,e_,b) for x,y,s,e_,b in e.get_points()])
        elif kind=='HATCH':
            for path in e.paths:
                if hasattr(path,'vertices'):
                    path.vertices=[(xmap(x),y,b) for x,y,b in path.vertices]
                else:
                    for edge in path.edges:
                        if hasattr(edge,'start') and hasattr(edge,'end'):
                            edge.start=point(edge.start)[:2]
                            edge.end=point(edge.end)[:2]
                        elif hasattr(edge,'center'):
                            edge.center=point(edge.center)[:2]
                        else:
                            raise ValueError('尚不支持此剖面边界类型')
        elif kind=='DIMENSION':
            for field in ('defpoint','defpoint2','defpoint3','defpoint4','defpoint5','text_midpoint'):
                p=e.dxf.get(field)
                if p is not None:
                    setattr(e.dxf,field,point(p))
            if entity_record(e)!=before:
                # 保持原尺寸样式与布点，将已有匿名块的坐标一同映射。
                for child in doc.blocks[e.dxf.geometry]:
                    t=child.dxftype()
                    if t=='LINE':
                        child.dxf.start=point(child.dxf.start)
                        child.dxf.end=point(child.dxf.end)
                    elif t in ('MTEXT','TEXT','INSERT'):
                        child.dxf.insert=point(child.dxf.insert)
                    elif t=='SOLID':
                        for key in ('vtx0','vtx1','vtx2','vtx3'):
                            setattr(child.dxf,key,point(getattr(child.dxf,key)))
                    elif t in ('CIRCLE','ARC'):
                        child.dxf.center=point(child.dxf.center)
                measurement=e.get_measurement()
                if isinstance(measurement,(int,float)):
                    e.dxf.actual_measurement=measurement
        elif kind in ('MTEXT','TEXT','TOLERANCE','INSERT'):
            e.dxf.insert=point(e.dxf.insert)
        if before!=entity_record(e):
            result.append({'handle':e.dxf.handle,'g5':'follow' if kind=='DIMENSION' else '',
                           'coordinate_map':list(zip(old,new))})
    return result
