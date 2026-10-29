import plotly.graph_objects as go
from ui.theme import tm

TEAL='#ED6B2C'; CORAL='#D7263D'; BLUE='#3C3E90'; AMBER='#C06443'; BG='#FFFFFF'

def style(fig,height=290):
    fig.update_layout(height=height,paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(family='Arial, Apple SD Gothic Neo, sans-serif',color='#424242',size=11),margin=dict(l=20,r=15,t=20,b=30),legend=dict(orientation='h',y=1.16,x=0,font=dict(size=10)),hoverlabel=dict(bgcolor='#203348',font_color='#eaf3fb'))
    fig.update_xaxes(gridcolor='#E2E2E7',zeroline=False,tickfont_size=10)
    fig.update_yaxes(gridcolor='#E2E2E7',zeroline=False,tickfont_size=10)
    return fig

def arrival_chart(o,height=310):
    pending=[x for x,c in o.containers.items() if not c.initial and o.statuses[x] not in ('RETRIEVED','EXCEPTION_LATE')][:8]
    fig=go.Figure()
    for i,cid in enumerate(pending):
        c=o.containers[cid];f=o.forecasts.get(cid);label=cid[-7:]
        fig.add_trace(go.Scatter(x=[c.booking_start/60,c.booking_end/60],y=[label,label],mode='lines',line=dict(color='#CFCFD6',width=12),name='예약 구간',showlegend=i==0,hovertemplate='예약 구간<extra></extra>'))
        if f:
            fig.add_trace(go.Scatter(x=[f.p10/60,f.p90/60],y=[label,label],mode='lines',line=dict(color=TEAL,width=4),name='ETA 구간',showlegend=i==0,hovertemplate='합성 ETA 구간<extra></extra>'))
            fig.add_trace(go.Scatter(x=[f.p50/60],y=[label],mode='markers',marker=dict(color=TEAL,size=9,symbol='diamond'),name='ETA 중앙값',showlegend=False,hovertemplate=tm(f.p50)+'<extra></extra>'))
    fig.add_vline(x=o.now/60,line_dash='dot',line_color=AMBER,annotation_text='현재',annotation_font_color=AMBER)
    ticks=list(range(0,121,15));fig.update_xaxes(tickvals=ticks,ticktext=[tm(x*60) for x in ticks],title=None)
    fig.update_yaxes(autorange='reversed')
    return style(fig,height)

def comparison_chart(results,height=285):
    fig=go.Figure();names=['예약 기반','ETA 기반','ETA + 선작업']
    fig.add_trace(go.Bar(name='작업 중 재취급',x=names,y=[results[p].metrics['REHANDLE'] for p in 'ABC'],marker_color=['#9AA0AC','#3C3E90','#ED6B2C'],text=[results[p].metrics['REHANDLE'] for p in 'ABC'],textposition='inside'))
    fig.add_trace(go.Bar(name='사전 이동',x=names,y=[results[p].metrics['PREMARSH'] for p in 'ABC'],marker_color=AMBER,text=[results[p].metrics['PREMARSH'] or '' for p in 'ABC'],textposition='inside'))
    fig.update_layout(barmode='stack',bargap=.55);fig.update_yaxes(title='완료된 추가 이동 / 회',dtick=5)
    return style(fig,height)

def cumulative_chart(results,height=265):
    fig=go.Figure()
    for p,color in zip('ABC',['#9AA0AC','#3C3E90',TEAL]):
        rows=[m for m in results[p].moves if m['completed'] and m['move_type'] in ('REHANDLE','PREMARSH')]
        fig.add_trace(go.Scatter(x=[0]+[m['end_at']/60 for m in sorted(rows,key=lambda m:m['end_at'])],y=list(range(len(rows)+1)),mode='lines',line=dict(color=color,width=2.5,shape='hv'),name={'A':'예약 기반','B':'ETA 기반','C':'ETA + 선작업'}[p]))
    fig.update_xaxes(title='시뮬레이션 경과 / 분');fig.update_yaxes(title='누적 추가 이동 / 회')
    return style(fig,height)
