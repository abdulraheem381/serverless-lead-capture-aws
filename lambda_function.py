import json
import boto3
import uuid
import os
import re
from datetime import datetime
from botocore.exceptions import ClientError

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ses = boto3.client('ses')

# Environment variables
TABLE_NAME = os.environ.get('TABLE_NAME', 'Leads')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')  # Must be verified in SES
NOTIFICATION_EMAIL = os.environ.get('NOTIFICATION_EMAIL')  # Admin email to receive alerts

def validate_input(data):
    """Basic validation for lead data."""
    required_fields = ['name', 'email', 'subject', 'message']
    
    # Check for missing fields
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            return False, f"Missing or empty required field: {field}"
    
    # Simple email regex validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, data['email']):
        return False, "Invalid email format"
        
    return True, None

def send_notification_email(lead_data):
    """Sends a professional HTML notification via SES."""
    if not SENDER_EMAIL or not NOTIFICATION_EMAIL:
        print("SES emails not configured, skipping email notification.")
        return

    subject = f"New Lead Captured: {lead_data['subject']}"
    
    # Professional HTML Body
    html_body = f"""
    <html>
    <head></head>
    <body style="font-family: sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #eee; padding: 20px; border-radius: 10px;">
            <h2 style="color: #4f46e5; border-bottom: 2px solid #4f46e5; padding-bottom: 10px;">New Lead Details</h2>
            <p><strong>Name:</strong> {lead_data['name']}</p>
            <p><strong>Email:</strong> {lead_data['email']}</p>
            <p><strong>Subject:</strong> {lead_data['subject']}</p>
            <p><strong>Message:</strong></p>
            <div style="background: #f9fafb; padding: 15px; border-radius: 5px; border-left: 4px solid #4f46e5;">
                {lead_data['message']}
            </div>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #999;">Received at: {lead_data['timestamp']}</p>
        </div>
    </body>
    </html>
    """

    try:
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [NOTIFICATION_EMAIL]},
            Message={
                'Subject': {'Data': subject},
                'Body': {
                    'Html': {'Data': html_body},
                    'Text': {'Data': f"New Lead from {lead_data['name']} ({lead_data['email']}): {lead_data['message']}"}
                }
            }
        )
    except ClientError as e:
        print(f"Error sending email: {e.response['Error']['Message']}")

def lambda_handler(event, context):
    """
    AWS Lambda handler for lead capture.
    Triggered by API Gateway POST request.
    """
    
    # Standard CORS Headers
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

    # Handle Preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            "statusCode": 200,
            "headers": headers,
            "body": ""
        }

    try:
        # 1. Parse JSON Body
        body = event.get('body')
        if not body:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({"error": "Request body is empty"})
            }
            
        data = json.loads(body)

        # 2. Validate Input
        is_valid, error_msg = validate_input(data)
        if not is_valid:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({"error": error_msg})
            }

        # 3. Prepare Lead Record
        lead_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        lead_item = {
            'id': lead_id,
            'timestamp': timestamp,
            'name': data['name'],
            'email': data['email'],
            'subject': data['subject'],
            'message': data['message'],
            'source': event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
        }

        # 4. Store in DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(Item=lead_item)

        # 5. Send Notification Email
        send_notification_email(lead_item)

        # 6. Return Success Response
        return {
            "statusCode": 201,
            "headers": headers,
            "body": json.dumps({
                "message": "Lead captured successfully",
                "id": lead_id
            })
        }

    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Invalid JSON format"})
        }
    except ClientError as e:
        print(f"AWS ClientError: {e}")
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({"error": "Failed to store lead data or send notification"})
        }
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({"error": "Internal server error"})
        }
