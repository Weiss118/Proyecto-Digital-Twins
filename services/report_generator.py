import io
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generar_pdf_auditoria(nombre_linea, dictamen_linea, descripcion_dictamen, lista_activos, fecha_str=None, auditor=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    story = []
    styles = getSampleStyleSheet()

    if not fecha_str:
        fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M hrs")

    header_title_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=10
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=12,
        spaceAfter=6
    )

    # Estilo de celda centrado
    cell_center_style = ParagraphStyle(
        'CellCenter',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        alignment=1  # 1 = Centrado
    )

    # 1. Encabezado del Informe
    story.append(Paragraph("REPORTE DE AUDITORÍA OPERACIONAL DE LÍNEA", header_title_style))
    story.append(Paragraph(f"<b>Línea:</b> {nombre_linea} | <b>Fecha:</b> {fecha_str} | <b>Auditor:</b> {auditor or 'Sistema PWA'}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=10))

    # 2. Resumen Ejecutivo
    color_dictamen = colors.HexColor('#10b981')
    if "IRREGULAR" in dictamen_linea:
        color_dictamen = colors.HexColor('#f59e0b')
    elif "ERROR" in dictamen_linea or "FALLA" in dictamen_linea:
        color_dictamen = colors.HexColor('#ef4444')

    dictamen_style = ParagraphStyle(
        'DictamenStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=color_dictamen,
        spaceAfter=4
    )

    story.append(Paragraph("1. Resumen de Diagnóstico General", section_heading))
    story.append(Paragraph(f"<b>DICTAMEN GLOBAL:</b> {dictamen_linea}", dictamen_style))
    story.append(Paragraph(f"<b>Evaluación Técnica:</b> {descripcion_dictamen}", styles['Normal']))
    story.append(Spacer(1, 10))

    story.append(Paragraph("2. Tablas de Telemetría Dinámica por Activo", section_heading))

    # 3. Tablas Dinámicas por Activo
    for equipo in lista_activos:
        nombre_equipo = str(equipo.get('nombre', '')).upper()
        equipo_id = str(equipo.get('id', '')).upper()
        
        # Marcado directo HTML en color blanco (#ffffff)
        titulo_html = f'<font color="#ffffff"><b>ID / ACTIVO: {nombre_equipo} ({equipo_id})</b></font>'
        
        tabla_datos = [
            [Paragraph(titulo_html, cell_center_style), ""]
        ]
        
        # Parámetros generales
        tabla_datos.append(["TIPO DE ACTIVO", str(equipo.get('tipo', 'N/A'))])
        tabla_datos.append(["ESTADO OPERATIVO", str(equipo.get('estado', 'N/A'))])
        tabla_datos.append(["SALUD DE ACTIVO", str(equipo.get('salud_individual', 'OPTIMO'))])
        
        # Variables dinámicas del equipo
        for var in equipo.get("variables", []):
            etiqueta = str(var.get("etiqueta", "")).upper()
            valor = var.get("valor", "")
            unidad = var.get("unidad", "")
            valor_str = f"{valor} {unidad}".strip()
            tabla_datos.append([etiqueta, valor_str])

        # Construcción de la tabla
        tabla = Table(tabla_datos, colWidths=[200, 340])
        tabla.setStyle(TableStyle([
            ('SPAN', (0,0), (1,0)),
            ('BACKGROUND', (0,0), (1,0), colors.HexColor('#0f172a')),
            ('ALIGN', (0,0), (1,0), 'CENTER'),
            ('BACKGROUND', (0,1), (0,-1), colors.HexColor('#f1f5f9')),
            ('FONTNAME', (0,1), (0,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        
        story.append(tabla)
        story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=6))
    pie_style = ParagraphStyle(
        'PieStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        textColor=colors.HexColor('#94a3b8'),
        alignment=1
    )
    story.append(Paragraph("Documento generado automáticamente con telemetría dinámica registrada en InfluxDB Cloud.", pie_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generar_csv_auditoria(nombre_linea, dictamen_linea, lista_activos):
    filas = []
    fecha_emision = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for equipo in lista_activos:
        act_id = equipo.get("id")
        act_nombre = equipo.get("nombre")
        act_tipo = equipo.get("tipo")
        act_estado = equipo.get("estado")
        act_salud = equipo.get("salud_individual", "OPTIMO")

        filas.append({
            "Linea_Trabajo": nombre_linea,
            "ID_Activo": act_id,
            "Nombre_Activo": act_nombre,
            "Tipo": act_tipo,
            "Estado": act_estado,
            "Salud": act_salud,
            "Parametro": "ESTADO OPERATIVO",
            "Valor": act_estado,
            "Unidad": "",
            "Fecha_Auditoria": fecha_emision
        })

        for var in equipo.get("variables", []):
            filas.append({
                "Linea_Trabajo": nombre_linea,
                "ID_Activo": act_id,
                "Nombre_Activo": act_nombre,
                "Tipo": act_tipo,
                "Estado": act_estado,
                "Salud": act_salud,
                "Parametro": var.get("etiqueta"),
                "Valor": var.get("valor"),
                "Unidad": var.get("unidad", ""),
                "Fecha_Auditoria": fecha_emision
            })

    df = pd.DataFrame(filas)
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False, encoding='utf-8-sig')
    buffer.seek(0)
    return buffer