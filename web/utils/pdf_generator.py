"""
PDF generation utilities for Travian Whispers.
Provides functions to generate receipts and other PDF documents.
"""
import logging
import io
from datetime import datetime

# Initialize logger
logger = logging.getLogger(__name__)

def generate_receipt_pdf(receipt_data):
    """
    Generate a PDF receipt.
    
    Args:
        receipt_data (dict): Receipt information
        
    Returns:
        bytes: PDF file content
    """
    try:
        # Try to import ReportLab
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
    except ImportError:
        # If ReportLab is not installed, raise a clear error
        logger.error("ReportLab library is not installed. Cannot generate PDF receipt.")
        raise ImportError("ReportLab library is required for PDF generation. Please install it with: pip install reportlab")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Create custom styles
    styles.add(ParagraphStyle(
        name='Title',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=1,  # Center alignment
        spaceAfter=12
    ))
    
    styles.add(ParagraphStyle(
        name='Header',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=6
    ))
    
    styles.add(ParagraphStyle(
        name='Normal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
    ))
    
    # Build content
    content = []
    
    # Add logo and header
    content.append(Paragraph("TRAVIAN WHISPERS", styles['Title']))
    content.append(Paragraph("RECEIPT", styles['Title']))
    content.append(Spacer(1, 0.25*inch))
    
    # Add receipt details
    receipt_date = receipt_data.get('date', datetime.now().strftime('%Y-%m-%d'))
    transaction_id = receipt_data.get('transaction_id', 'Unknown')
    order_id = receipt_data.get('order_id', 'Unknown')
    
    content.append(Paragraph(f"Receipt Date: {receipt_date}", styles['Normal']))
    content.append(Paragraph(f"Transaction ID: {transaction_id}", styles['Normal']))
    content.append(Paragraph(f"Order ID: {order_id}", styles['Normal']))
    content.append(Spacer(1, 0.25*inch))
    
    # Customer information
    content.append(Paragraph("CUSTOMER INFORMATION", styles['Header']))
    content.append(Paragraph(f"Name: {receipt_data.get('user_name', 'Unknown')}", styles['Normal']))
    content.append(Paragraph(f"Email: {receipt_data.get('user_email', 'Unknown')}", styles['Normal']))
    content.append(Spacer(1, 0.25*inch))
    
    # Purchase information
    content.append(Paragraph("PURCHASE INFORMATION", styles['Header']))
    
    # Create a table for the purchase
    data = [
        ['Item', 'Billing Period', 'Amount'],
        [
            receipt_data.get('plan_name', 'Subscription Plan'), 
            receipt_data.get('billing_period', 'Monthly'), 
            f"${receipt_data.get('amount', 0):.2f}"
        ]
    ]
    
    # Calculate total
    data.append(['', 'Subtotal', f"${receipt_data.get('amount', 0):.2f}"])
    data.append(['', 'Tax', '$0.00'])
    data.append(['', 'Total', f"${receipt_data.get('amount', 0):.2f}"])
    
    # Create the table
    table = Table(data, colWidths=[3*inch, 2*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (2, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (2, 0), colors.black),
        ('ALIGN', (0, 0), (2, 0), 'CENTER'),
        ('ALIGN', (1, 1), (2, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (2, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (2, 0), 12),
        ('GRID', (0, 0), (2, -1), 1, colors.black),
        ('LINEBELOW', (0, -1), (2, -1), 1.5, colors.black),
        ('BACKGROUND', (0, -1), (2, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (2, -1), 'Helvetica-Bold'),
    ]))
    
    content.append(table)
    content.append(Spacer(1, 0.25*inch))
    
    # Payment information
    content.append(Paragraph("PAYMENT INFORMATION", styles['Header']))
    content.append(Paragraph(f"Payment Method: {receipt_data.get('payment_method', 'Unknown').title()}", styles['Normal']))
    content.append(Paragraph(f"Payment Status: Completed", styles['Normal']))
    content.append(Spacer(1, 0.5*inch))
    
    # Footer
    content.append(Paragraph("Thank you for your business!", styles['Normal']))
    content.append(Paragraph("This is an automatically generated receipt. For any questions, please contact support@travianwhispers.com", styles['Normal']))
    
    # Build the PDF
    doc.build(content)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

def generate_subscription_summary_pdf(user_data, subscription_data, transaction_history):
    """
    Generate a PDF summary of a user's subscription.
    
    Args:
        user_data (dict): User information
        subscription_data (dict): Subscription details
        transaction_history (list): List of transactions
        
    Returns:
        bytes: PDF file content
    """
    try:
        # Try to import ReportLab
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
    except ImportError:
        # If ReportLab is not installed, raise a clear error
        logger.error("ReportLab library is not installed. Cannot generate PDF summary.")
        raise ImportError("ReportLab library is required for PDF generation. Please install it with: pip install reportlab")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Create custom styles
    styles.add(ParagraphStyle(
        name='Title',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=1,  # Center alignment
        spaceAfter=12
    ))
    
    styles.add(ParagraphStyle(
        name='Header',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=6
    ))
    
    styles.add(ParagraphStyle(
        name='Normal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
    ))
    
    # Build content
    content = []
    
    # Add logo and header
    content.append(Paragraph("TRAVIAN WHISPERS", styles['Title']))
    content.append(Paragraph("SUBSCRIPTION SUMMARY", styles['Title']))
    content.append(Spacer(1, 0.25*inch))
    
    # Add user details
    content.append(Paragraph("ACCOUNT INFORMATION", styles['Header']))
    content.append(Paragraph(f"Username: {user_data.get('username', 'Unknown')}", styles['Normal']))
    content.append(Paragraph(f"Email: {user_data.get('email', 'Unknown')}", styles['Normal']))
    content.append(Paragraph(f"Account Created: {user_data.get('created_at', 'Unknown')}", styles['Normal']))
    content.append(Spacer(1, 0.25*inch))
    
    # Subscription information
    content.append(Paragraph("SUBSCRIPTION DETAILS", styles['Header']))
    content.append(Paragraph(f"Plan: {subscription_data.get('plan_name', 'None')}", styles['Normal']))
    content.append(Paragraph(f"Status: {subscription_data.get('status', 'Inactive').title()}", styles['Normal']))
    content.append(Paragraph(f"Start Date: {subscription_data.get('start_date', 'N/A')}", styles['Normal']))
    content.append(Paragraph(f"End Date: {subscription_data.get('end_date', 'N/A')}", styles['Normal']))
    content.append(Paragraph(f"Billing Period: {subscription_data.get('billing_period', 'Monthly').title()}", styles['Normal']))
    content.append(Paragraph(f"Auto-Renew: {'Enabled' if subscription_data.get('auto_renew', False) else 'Disabled'}", styles['Normal']))
    content.append(Spacer(1, 0.25*inch))
    
    # Transaction history
    content.append(Paragraph("TRANSACTION HISTORY", styles['Header']))
    
    if transaction_history:
        # Create table for transactions
        table_data = [['Date', 'Plan', 'Amount', 'Status']]
        
        # Add transactions to the table
        for tx in transaction_history:
            table_data.append([
                tx.get('date', 'Unknown'),
                tx.get('plan', 'Unknown'),
                f"${tx.get('amount', 0):.2f}",
                tx.get('status', 'Unknown').title()
            ])
        
        # Create the table
        table = Table(table_data, colWidths=[1.5*inch, 2*inch, 1*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        content.append(table)
    else:
        content.append(Paragraph("No transactions found", styles['Normal']))
    
    content.append(Spacer(1, 0.25*inch))
    
    # Summary footer
    content.append(Paragraph("SUMMARY", styles['Header']))
    total_spent = sum(tx.get('amount', 0) for tx in transaction_history if tx.get('status') == 'completed')
    content.append(Paragraph(f"Total Amount Spent: ${total_spent:.2f}", styles['Normal']))
    content.append(Paragraph(f"Total Transactions: {len(transaction_history)}", styles['Normal']))
    
    content.append(Spacer(1, 0.5*inch))
    
    # Footer
    content.append(Paragraph("This is an automatically generated summary. For any questions about your subscription, please contact support@travianwhispers.com", styles['Normal']))
    
    # Build the PDF
    doc.build(content)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data
