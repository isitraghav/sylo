# Flask endpoints for anomaly update functionality
# Add these to your main Flask application

from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import base64
import io
from PIL import Image as PILImage
import requests

# Initialize Flask app
app = Flask(__name__)

# Database models (adapt to your existing database structure)
# Assuming you have a database connection and models

@app.route('/api/update_anomaly_details', methods=['POST'])
def update_anomaly_details():
    """Update anomaly details with verification information"""
    try:
        # Get form data
        audit_id = request.form.get('audit_id')
        anomaly_id = request.form.get('anomaly_id')
        issue_type = request.form.get('issueType')
        status = request.form.get('status')
        voc_module = request.form.get('vocModule')
        module_serial = request.form.get('moduleSerial')
        verified_at = request.form.get('verifiedAt')
        verified_by = request.form.get('verifiedBy')
        action = request.form.get('action')
        remarks = request.form.get('remarks')
        
        # Handle file upload
        attachment = request.files.get('attachment')
        attachment_path = None
        
        if attachment and attachment.filename:
            filename = secure_filename(attachment.filename)
            # Create uploads directory if it doesn't exist
            upload_dir = os.path.join('uploads_data', 'anomaly_updates')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            attachment_path = os.path.join(upload_dir, f"{timestamp}_{filename}")
            attachment.save(attachment_path)
        
        # Create update record
        update_data = {
            'audit_id': audit_id,
            'anomaly_id': anomaly_id,
            'issue_type': issue_type,
            'status': status,
            'voc_module': voc_module,
            'module_serial': module_serial,
            'verified_at': verified_at,
            'verified_by': verified_by,
            'action': action,
            'remarks': remarks,
            'attachment_path': attachment_path,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        
        # Save to database (implement your database logic here)
        # Example: 
        # db.anomaly_updates.insert_one(update_data)
        # or using SQLAlchemy:
        # new_update = AnomalyUpdate(**update_data)
        # db.session.add(new_update)
        # db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Anomaly details updated successfully',
            'data': update_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error updating anomaly details: {str(e)}'
        }), 500

@app.route('/api/generate_anomaly_pdf', methods=['POST'])
def generate_anomaly_pdf():
    """Generate comprehensive PDF report for anomaly"""
    try:
        data = request.get_json()
        image_path = data.get('image_path')
        image_name = data.get('image_name')
        properties = data.get('properties')
        audit_id = data.get('audit_id')
        
        # Create PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#2e7d32')
        )
        
        normal_style = styles['Normal']
        
        # Build PDF content
        story = []
        
        # Title
        story.append(Paragraph("Thermal Anomaly Report", title_style))
        story.append(Spacer(1, 20))
        
        # Anomaly Information
        story.append(Paragraph("Anomaly Information", heading_style))
        
        # Basic details table
        basic_data = [
            ['Anomaly ID:', properties.get('ID', 'N/A')],
            ['Anomaly Type:', properties.get('Anomaly', 'N/A')],
            ['Severity:', properties.get('Severity', 'N/A')],
            ['Status:', properties.get('status', 'Pending')],
            ['Date:', properties.get('Date', 'N/A')],
            ['Time:', properties.get('Time', 'N/A')],
        ]
        
        basic_table = Table(basic_data, colWidths=[2*inch, 3*inch])
        basic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(basic_table)
        story.append(Spacer(1, 20))
        
        # Technical Details
        story.append(Paragraph("Technical Details", heading_style))
        
        tech_data = [
            ['ΔT (T2 - T1):', properties.get('Hotspot', 'N/A')],
            ['Irradiance:', properties.get('Irradian', 'N/A')],
            ['Module Make:', properties.get('make', 'N/A')],
            ['Module Watt:', properties.get('Wat', 'N/A')],
            ['Barcode Serial:', properties.get('barcode', 'N/A')],
        ]
        
        tech_table = Table(tech_data, colWidths=[2*inch, 3*inch])
        tech_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(tech_table)
        story.append(Spacer(1, 20))
        
        # Location Details
        story.append(Paragraph("Location Details", heading_style))
        
        location_data = [
            ['Latitude:', properties.get('Latitude', 'N/A')],
            ['Longitude:', properties.get('Longitude', 'N/A')],
            ['Block:', properties.get('Block', 'N/A')],
            ['String:', properties.get('String', 'N/A')],
            ['Module:', properties.get('panel', 'N/A')],
        ]
        
        location_table = Table(location_data, colWidths=[2*inch, 3*inch])
        location_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(location_table)
        story.append(Spacer(1, 30))
        
        # Thermal Image
        story.append(Paragraph("Thermal Image", heading_style))
        
        # Try to add the image
        try:
            if image_path.startswith('http'):
                # Download image from URL
                response = requests.get(image_path)
                if response.status_code == 200:
                    image_data = io.BytesIO(response.content)
                    pil_img = PILImage.open(image_data)
                    
                    # Resize image to fit page
                    max_width, max_height = 4*inch, 3*inch
                    pil_img.thumbnail((max_width, max_height), PILImage.Resampling.LANCZOS)
                    
                    # Convert back to BytesIO
                    img_buffer = io.BytesIO()
                    pil_img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    
                    # Add to PDF
                    img = Image(img_buffer, width=pil_img.width, height=pil_img.height)
                    story.append(img)
                else:
                    story.append(Paragraph("Image could not be loaded", normal_style))
            else:
                # Local file path
                if os.path.exists(image_path):
                    img = Image(image_path, width=4*inch, height=3*inch)
                    story.append(img)
                else:
                    story.append(Paragraph("Image file not found", normal_style))
        except Exception as img_error:
            story.append(Paragraph(f"Error loading image: {str(img_error)}", normal_style))
        
        story.append(Spacer(1, 20))
        
        # Get update details if available
        # update_details = get_anomaly_update_details(audit_id, image_name)
        # For demo purposes, we'll check if there are update details
        update_details = None  # Replace with actual database query
        
        if update_details:
            story.append(Paragraph("Update Details", heading_style))
            
            update_data = [
                ['Issue Type:', update_details.get('issue_type', 'N/A')],
                ['Status:', update_details.get('status', 'N/A')],
                ['Voc of Module:', update_details.get('voc_module', 'N/A')],
                ['Module Serial:', update_details.get('module_serial', 'N/A')],
                ['Verified At:', update_details.get('verified_at', 'N/A')],
                ['Verified By:', update_details.get('verified_by', 'N/A')],
                ['Action Taken:', update_details.get('action', 'N/A')],
            ]
            
            update_table = Table(update_data, colWidths=[2*inch, 3*inch])
            update_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(update_table)
            
            if update_details.get('remarks'):
                story.append(Spacer(1, 12))
                story.append(Paragraph("Remarks:", heading_style))
                story.append(Paragraph(update_details.get('remarks'), normal_style))
        
        # Footer
        story.append(Spacer(1, 30))
        footer_text = f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        story.append(Paragraph(footer_text, normal_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'anomaly_report_{image_name}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error generating PDF: {str(e)}'
        }), 500

# Helper function to get update details (implement based on your database)
def get_anomaly_update_details(audit_id, anomaly_id):
    """
    Fetch update details for a specific anomaly
    Implement this based on your database structure
    """
    # Example implementation:
    # return db.anomaly_updates.find_one({
    #     'audit_id': audit_id,
    #     'anomaly_id': anomaly_id
    # })
    return None

# Database schema example (for reference)
"""
CREATE TABLE anomaly_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id VARCHAR(255) NOT NULL,
    anomaly_id VARCHAR(255) NOT NULL,
    issue_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    voc_module VARCHAR(100) NOT NULL,
    module_serial VARCHAR(100) NOT NULL,
    verified_at DATE NOT NULL,
    verified_by VARCHAR(100) NOT NULL,
    action TEXT NOT NULL,
    remarks TEXT,
    attachment_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
"""
