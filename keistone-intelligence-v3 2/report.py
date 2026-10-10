import io
from collections import Counter
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

INK=colors.HexColor('#172033')
PURPLE=colors.HexColor('#6159d8')

def build_pdf(result):
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=(612,792),rightMargin=42,leftMargin=42,topMargin=46,bottomMargin=44)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BrandKK',fontName='Helvetica-Bold',fontSize=12,textColor=PURPLE,spaceAfter=14))
    styles.add(ParagraphStyle(name='HeroKK',fontName='Helvetica-Bold',fontSize=23,leading=28,textColor=INK,spaceAfter=12))
    styles.add(ParagraphStyle(name='BodyKK',fontName='Helvetica',fontSize=9,leading=14,textColor=INK,spaceAfter=9))
    styles.add(ParagraphStyle(name='SectionKK',fontName='Helvetica-Bold',fontSize=13,textColor=INK,spaceBefore=14,spaceAfter=9))
    styles.add(ParagraphStyle(name='SmallKK',fontName='Helvetica',fontSize=8,leading=11,textColor=INK,spaceAfter=6))
    P=lambda x,style='BodyKK':Paragraph(escape(str(x)),styles[style])
    story=[P('KEISTONE KOLLECTIVE','BrandKK'),P('360° Website Intelligence Audit','HeroKK'),P(result['url']),P('Crawl date: '+result['created_at']),Spacer(1,10)]
    counts=Counter(f['severity'] for f in result['findings'])
    data=[['SITE HEALTH','CRAWLED PAGES','ERRORS','WARNINGS'],[f"{result['score']}/100",str(result['crawled']),str(counts['error']),str(counts['warning'])]]
    t=Table(data,colWidths=[132]*4,rowHeights=[25,42]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f2f3f9')),('TEXTCOLOR',(0,0),(-1,0),INK),('TEXTCOLOR',(0,1),(-1,1),PURPLE),('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),8),('FONTSIZE',(0,1),(-1,1),20),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story.extend([t,Spacer(1,14),P('Executive overview','SectionKK'),P(f"Audited {result['crawled']} pages and identified {len(result['findings'])} findings. The score is an indicative technical health measure, not an estimate of search traffic, revenue, or SEMrush's proprietary score."),P(result['methodology'],'SmallKK')])
    if result.get('capped'): story.append(P('Crawl reached the configured page limit; findings do not cover the entire website.'))
    story.append(P('Prioritized findings','SectionKK'))
    sorted_findings=sorted(result['findings'],key=lambda f:{'error':0,'warning':1,'notice':2}.get(f['severity'],3))
    if not sorted_findings: story.append(P('No issues detected within the pages and checks covered.'))
    for i,f in enumerate(sorted_findings[:80],1):
        story.append(KeepTogether([P(f"{i}. [{f['severity'].upper()}] {f['title']}",'SmallKK'),P('URL: '+f['url'],'SmallKK'),P('Evidence: '+(f['detail'] or 'Detected by HTML/HTTP analysis'),'SmallKK'),P('Recommendation: '+f['fix'],'SmallKK'),Spacer(1,7)]))
    if len(sorted_findings)>80: story.append(P(f"Showing first 80 of {len(sorted_findings)} findings. View the dashboard for the full list."))
    story.extend([P('Audit limitations','SectionKK'),P('This crawl analyzes accessible HTML and HTTP responses only. It does not verify actual traffic, backlinks, keyword rankings, conversions, visual design quality, JavaScript-rendered content, or complete accessibility compliance. Findings should be verified before remediation.')])
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.grey)
        canvas.drawString(42,27,'Keistone Kollective • Website Intelligence')
        canvas.drawRightString(570,27,f'Page {doc.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()
