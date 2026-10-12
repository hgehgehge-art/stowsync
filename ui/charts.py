import plotly.graph_objects as go
from engine.yard import blockers, rank
from ui.theme import tm

TEAL='#64d8c5'; CORAL='#e78095'; BLUE='#698fd0'; AMBER='#e6b877'; BG='#101d2d'

def style(fig,height=290):
    fig.update_layout(height=height,paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(family='Arial, Apple SD Gothic Neo, sans-serif',color='#a8bdd0',size=11),margin=dict(l=20,r=15,t=20,b=30),legend=dict(orientation='h',y=1.16,x=0,font=dict(size=10)),hoverlabel=dict(bgcolor='#203348',font_color='#eaf3fb'))
    fig.update_xaxes(gridcolor='#25384b',zeroline=False,tickfont_size=10)
    fig.update_yaxes(gridcolor='#25384b',zeroline=False,tickfont_size=10)
    return fig

def coords(stack):
    block,bay,row=stack.split('-')
    return (int(bay)-1)*2.35 + (0 if block=='A1' else 6.2), (int(row)-1)*1.17

def cube(fig,x,y,z,dx,dy,dz,color,text='',alpha=1,edges=True):
    xs=[x,x+dx,x+dx,x,x,x+dx,x+dx,x];ys=[y,y,y+dy,y+dy,y,y,y+dy,y+dy];zs=[z,z,z,z,z+dz,z+dz,z+dz,z+dz]
    fig.add_trace(go.Mesh3d(x=xs,y=ys,z=zs,i=[0,0,0,0,1,1,2,2,3,3,4,4],j=[1,2,4,5,2,5,3,6,0,7,5,6],k=[2,3,5,1,5,6,6,7,7,4,6,7],color=color,opacity=alpha,flatshading=True,lighting=dict(ambient=.75,diffuse=.75,specular=.15,roughness=.8),lightposition=dict(x=-80,y=-50,z=130),hovertemplate=text+'<extra></extra>' if text else None,hoverinfo=None if text else 'skip',showscale=False,name=''))
    if edges:
        ex=[];ey=[];ez=[]
        for a,b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]:
            ex.extend([xs[a],xs[b],None]);ey.extend([ys[a],ys[b],None]);ez.extend([zs[a],zs[b],None])
        fig.add_trace(go.Scatter3d(x=ex,y=ey,z=ez,mode='lines',line=dict(color='#b6d4e5' if color==TEAL else '#8da6b3',width=1),opacity=.3,hoverinfo='skip',showlegend=False))

def yard_figure(o,selected=None,target=None,height=355,block=None):
    fig=go.Figure();risks,_=blockers(o.yard,o.plan)
    priority=set(sorted(o.plan,key=lambda x:rank(o.plan,x))[:max(1,int(len(o.plan)*.3))])
    cube(fig,-.7,-.9,-.2,11.8,5.0,.12,'#152d40',edges=False)
    # Pier marking and crane rails give the model an industrial rather than chart-like context.
    for x in [-.35,4.65,5.85,10.85]:
        fig.add_trace(go.Scatter3d(x=[x,x],y=[-.5,3.5],z=[-.06,-.06],mode='lines',line=dict(color='#3a5a6a',width=3),hoverinfo='skip',showlegend=False))
    for key,items in o.yard.items():
        x,y=coords(key)
        if block and not key.startswith(block):continue
        fig.add_trace(go.Scatter3d(x=[x,x+2.05,x+2.05,x,x],y=[y,y,y+.92,y+.92,y],z=[-.04]*5,mode='lines',line=dict(color='#365365',width=2),hoverinfo='skip',showlegend=False))
        for i,cid in enumerate(items):
            c=o.containers[cid];p=o.plan.get(cid)
            color=TEAL if cid==selected else CORAL if cid in risks else AMBER if cid in priority else BLUE
            if o.statuses.get(cid)=='IN_MOVE':color=TEAL
            text=f'{cid}<br>{key}-{i+1:02d}<br>선적 순위 {p.sequence if p else "미정"} · {c.weight_t}t'
            cube(fig,x,y,i*.57,2.02,.9,.52,color,text)
            # Corrugation lines on visible long face.
            xx=[];yy=[];zz=[]
            for k in range(1,10):
                xx.extend([x+k*.19,x+k*.19,None]);yy.extend([y-.006,y-.006,None]);zz.extend([i*.57+.07,i*.57+.44,None])
            fig.add_trace(go.Scatter3d(x=xx,y=yy,z=zz,mode='lines',line=dict(color='#1c3649',width=2),opacity=.27,hoverinfo='skip',showlegend=False))
    if target:
        key,tier=target;x,y=coords(key)
        cube(fig,x,y,(tier-1)*.57,2.02,.9,.52,TEAL,'추천 위치 '+key+f'-{tier:02d}',alpha=.38)
    # A minimal gantry frame over each block.
    for offset in [0,6.2]:
        x=offset+3.4
        fig.add_trace(go.Scatter3d(x=[x,x,x,x],y=[-.4,-.4,3.5,3.5],z=[0,3,3,0],mode='lines',line=dict(color='#6a8598',width=6),hoverinfo='skip',showlegend=False))
        fig.add_trace(go.Scatter3d(x=[x,x],y=[1.1,1.1],z=[3,2.65],mode='lines',line=dict(color='#aac1ce',width=2),hoverinfo='skip',showlegend=False))
    fig.add_trace(go.Scatter3d(x=[2.1,8.3],y=[-.8,-.8],z=[0,0],mode='text',text=['BLOCK A1','BLOCK B1'],textfont=dict(size=12,color='#c2d7e6'),hoverinfo='skip',showlegend=False))
    fig.update_layout(height=height,paper_bgcolor='rgba(0,0,0,0)',margin=dict(l=0,r=0,t=0,b=0),showlegend=False,scene=dict(bgcolor='rgba(0,0,0,0)',xaxis=dict(visible=False,range=[-.7,11.1]),yaxis=dict(visible=False,range=[-1,4]),zaxis=dict(visible=False,range=[-.2,3.4]),aspectmode='manual',aspectratio=dict(x=2.6,y=1.2,z=.72),camera=dict(eye=dict(x=1.38,y=-1.9,z=1.3),projection=dict(type='orthographic'))),uirevision='stowsync-yard-v1')
    return fig

def arrival_chart(o,height=310):
    pending=[x for x,c in o.containers.items() if not c.initial and o.statuses[x] not in ('RETRIEVED','EXCEPTION_LATE')][:8]
    fig=go.Figure()
    for i,cid in enumerate(pending):
        c=o.containers[cid];f=o.forecasts.get(cid);label=cid[-7:]
        fig.add_trace(go.Scatter(x=[c.booking_start/60,c.booking_end/60],y=[label,label],mode='lines',line=dict(color='#3d536e',width=12),name='예약 구간',showlegend=i==0,hovertemplate='예약 구간<extra></extra>'))
        if f:
            fig.add_trace(go.Scatter(x=[f.p10/60,f.p90/60],y=[label,label],mode='lines',line=dict(color=TEAL,width=4),name='ETA 구간',showlegend=i==0,hovertemplate='합성 ETA 구간<extra></extra>'))
            fig.add_trace(go.Scatter(x=[f.p50/60],y=[label],mode='markers',marker=dict(color=TEAL,size=9,symbol='diamond'),name='ETA 중앙값',showlegend=False,hovertemplate=tm(f.p50)+'<extra></extra>'))
    fig.add_vline(x=o.now/60,line_dash='dot',line_color=AMBER,annotation_text='현재',annotation_font_color=AMBER)
    ticks=list(range(0,121,15));fig.update_xaxes(tickvals=ticks,ticktext=[tm(x*60) for x in ticks],title=None)
    fig.update_yaxes(autorange='reversed')
    return style(fig,height)

def comparison_chart(results,height=285):
    fig=go.Figure();names=['예약 기반','ETA 기반','ETA + 선작업']
    fig.add_trace(go.Bar(name='작업 중 재취급',x=names,y=[results[p].metrics['REHANDLE'] for p in 'ABC'],marker_color=['#53718f','#558caf','#54bead'],text=[results[p].metrics['REHANDLE'] for p in 'ABC'],textposition='inside'))
    fig.add_trace(go.Bar(name='사전 이동',x=names,y=[results[p].metrics['PREMARSH'] for p in 'ABC'],marker_color=AMBER,text=[results[p].metrics['PREMARSH'] or '' for p in 'ABC'],textposition='inside'))
    fig.update_layout(barmode='stack',bargap=.55);fig.update_yaxes(title='완료된 추가 이동 / 회',dtick=5)
    return style(fig,height)

def cumulative_chart(results,height=265):
    fig=go.Figure()
    for p,color in zip('ABC',['#667f9d','#759ee8',TEAL]):
        rows=[m for m in results[p].moves if m['completed'] and m['move_type'] in ('REHANDLE','PREMARSH')]
        fig.add_trace(go.Scatter(x=[0]+[m['end_at']/60 for m in sorted(rows,key=lambda m:m['end_at'])],y=list(range(len(rows)+1)),mode='lines',line=dict(color=color,width=2.5,shape='hv'),name={'A':'예약 기반','B':'ETA 기반','C':'ETA + 선작업'}[p]))
    fig.update_xaxes(title='시뮬레이션 경과 / 분');fig.update_yaxes(title='누적 추가 이동 / 회')
    return style(fig,height)
