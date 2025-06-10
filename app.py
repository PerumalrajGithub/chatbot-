import os 
from dotenv import load_dotenv 
from datetime import datetime, timedelta 
import smtplib 
from email.message import EmailMessage 
import openpyxl 
import schedule 
import threading 
import time 
import boto3 
  
from slack_bolt import App 
from slack_bolt.adapter.socket_mode import SocketModeHandler 
from langchain_community.chat_models import ChatOpenAI 
from langchain.chains import LLMChain 
from langchain.prompts import PromptTemplate 
from langchain.chains.conversation.memory import ConversationBufferWindowMemory 
  
# Load environment variables 
load_dotenv(r"c:\AWS SLACK\.env") 
  
app = App(token=os.environ["SLACK_BOT_TOKEN"]) 
ce_client = boto3.client('ce') 
DEFAULT_REGION = "us-east-1" 
REGION_OPTIONS = ["us-east-1", "us-east-2", "us-west-1", "us-west-2", "ap-south-1"] 
  
# LangChain GPT setup 
template = """Assistant is a large language model trained by OpenRouteAI. 
{history} 
Human: {human_input} 
Assistant:""" 
  
prompt = PromptTemplate(input_variables=["history", "human_input"], 
template=template) 
chatgpt_chain = LLMChain( 
    llm=ChatOpenAI( 
        base_url="https://openrouter.ai/api/v1", 
        api_key=os.getenv("OPENAI_API_KEY"), 
        model_name="openai/gpt-3.5-turbo", 
        temperature=0 
    ), 
    prompt=prompt, 
    verbose=False, 
    memory=ConversationBufferWindowMemory(k=2) 
) 
  
# --- AWS Utilities ---
  
def list_s3_buckets(): 
    try: 
        s3 = boto3.client("s3") 
        buckets = s3.list_buckets().get('Buckets', []) 
        return "🪣 *S3 Buckets:*\n" + "\n".join(b['Name'] for b in buckets) if buckets 
else "No buckets found." 
    except Exception as e: 
        return f"🚨 S3 error: {e}" 
  
def list_ec2_instances(region): 
    try: 
        ec2 = boto3.client("ec2", region_name=region) 
        reservations = ec2.describe_instances().get('Reservations', []) 
        instances = [] 
        for r in reservations: 
            for i in r['Instances']: 
                state = i.get('State', {}).get('Name', 'unknown') 
                inst_id = i.get('InstanceId', 'N/A') 
                inst_type = i.get('InstanceType', 'N/A') 
                instances.append(f"{inst_id} (Type: {inst_type}, State: {state})") 
        return f"🖥️ *EC2 Instances in {region}:*\n" + "\n".join(instances) if 
instances else "No instances found." 
    except Exception as e: 
        return f"🚨 EC2 error: {e}" 
  
def list_vpcs(region): 
    try: 
        ec2 = boto3.client("ec2", region_name=region) 
        vpcs = ec2.describe_vpcs().get('Vpcs', []) 
        return "🌐 *VPCs:*\n" + "\n".join(v['VpcId'] for v in vpcs) if vpcs else "No 
VPCs found." 
    except Exception as e: 
        return f"🚨 VPC error: {e}" 
  
def list_nat_gateways(region): 
    try: 
        ec2 = boto3.client("ec2", region_name=region) 
        gateways = ec2.describe_nat_gateways().get('NatGateways', []) 
        return "🚪 *NAT Gateways:*\n" + "\n".join(g['NatGatewayId'] for g in 
gateways) if gateways else "No NAT Gateways found." 
    except Exception as e: 
        return f"🚨 NAT Gateway error: {e}" 
  
def list_eks_clusters(region): 
    try: 
        eks = boto3.client("eks", region_name=region) 
        clusters = eks.list_clusters().get('clusters', []) 
        return "☸️ *EKS Clusters:*\n" + "\n".join(clusters) if clusters else "No EKS 
clusters found." 
    except Exception as e: 
        return f"🚨 EKS error: {e}" 
def list_ecr_repositories(region): 
    try: 
        ecr = boto3.client("ecr", region_name=region) 
        repos = ecr.describe_repositories().get('repositories', []) 
        return "📦 *ECR Repositories:*\n" + "\n".join(r['repositoryName'] for r in 
repos) if repos else "No ECR repositories found." 
    except Exception as e: 
        return f"🚨 ECR error: {e}" 
  
def get_aws_billing(period="monthly"): 
    try: 
        now = datetime.utcnow() 
        if period == "monthly": 
            start = now.replace(day=1).strftime('%Y-%m-%d') 
            end = now.strftime('%Y-%m-%d') 
            gran = 'MONTHLY' 
        elif period == "weekly": 
            end = now.strftime('%Y-%m-%d') 
            start = (now - timedelta(days=7)).strftime('%Y-%m-%d') 
            gran = 'DAILY' 
        else: 
            return "🚨 Invalid billing period." 
  
        resp = ce_client.get_cost_and_usage( 
            TimePeriod={'Start': start, 'End': end}, 
            Granularity=gran, 
            Metrics=['UnblendedCost'] 
        ) 
  
        if gran == 'MONTHLY': 
            amt = resp['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'] 
            unit = resp['ResultsByTime'][0]['Total']['UnblendedCost']['Unit'] 
            return f"💰 *AWS Monthly Billing:* {amt} {unit}" 
        else: 
            total = sum(float(day['Total']['UnblendedCost']['Amount']) for day in 
resp['ResultsByTime']) 
            unit = resp['ResultsByTime'][0]['Total']['UnblendedCost']['Unit'] 
            return f"💰 *AWS Weekly Billing:* {total:.2f} {unit}" 
    except Exception as e: 
        return f"🚨 Billing error: {e}" 
  
def get_high_cost_resources(): 
    return "🔍 *High Cost Resources:*\n- EC2: i-1234567890abcdef0 ($150)\n- RDS: db
xyz123 ($120)\n- S3: Bucket 'backup-data' ($90)" 
  
# --- Scheduled Email Report --- 
  
def generate_billing_excel(filepath="aws_billing_report.xlsx"): 
    now = datetime.utcnow() 
    start = now.replace(day=1).strftime('%Y-%m-%d') 
    end = now.strftime('%Y-%m-%d') 
  
    try:
 response = ce_client.get_cost_and_usage( 
            TimePeriod={'Start': start, 'End': end}, 
            Granularity='MONTHLY', 
            Metrics=['UnblendedCost'], 
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}] 
        ) 
  
        wb = openpyxl.Workbook() 
        ws = wb.active 
        ws.title = "AWS Billing" 
        ws.append(["Service", "Cost (USD)"]) 
  
        total_cost = 0.0 
        for group in response['ResultsByTime'][0]['Groups']: 
            service = group['Keys'][0] 
            amount = float(group['Metrics']['UnblendedCost']['Amount']) 
            total_cost += amount 
            ws.append([service, round(amount, 2)]) 
  
        ws.append(["Total", round(total_cost, 2)]) 
        wb.save(filepath) 
        return filepath 
    except Exception as e: 
        print("❌ Excel generation error:", e) 
        return None 
  
def get_running_ec2_summary(): 
    result = [] 
    for region in REGION_OPTIONS: 
        try: 
            ec2 = boto3.client("ec2", region_name=region) 
            reservations = ec2.describe_instances(Filters=[{'Name': 'instance-state
name', 'Values': ['running']}]) 
            for r in reservations.get('Reservations', []): 
                for i in r['Instances']: 
                    result.append(f"{region}: {i['InstanceId']} 
({i['InstanceType']})") 
        except Exception as e: 
            result.append(f"{region}: Error - {e}") 
    return "\n".join(result) if result else "No running EC2 instances found." 
  
def send_email(): 
    print("📤 Sending scheduled AWS email report...") 
  
    sender = os.getenv("EMAIL_SENDER") 
    password = os.getenv("EMAIL_PASSWORD") 
    recipient = os.getenv("MANAGER_EMAIL", "pnyn96@gmail.com") 
    smtp_server = os.getenv("EMAIL_SMTP", "smtp.gmail.com") 
    smtp_port = int(os.getenv("EMAIL_PORT", 587)) 
  
    billing_file = generate_billing_excel() 
    ec2_summary = get_running_ec2_summary() 
  
    if not billing_file:
print("❌ Billing file not generated.") 
        return 
  
    msg = EmailMessage() 
    msg["Subject"] = "AWS Report" 
    msg["From"] = sender 
    msg["To"] = recipient 
    msg.set_content(f"""Hello, 
  
Here is your scheduled AWS report: 
  
�
� Running EC2 Instances: 
{ec2_summary} 
  
�
� Monthly Billing Report (attached) 
  
Regards,   
AWS Bot 
""") 
  
    with open(billing_file, "rb") as f: 
        msg.add_attachment( 
            f.read(), maintype="application", 
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            filename="aws_billing_report.xlsx" 
        ) 
  
    try: 
        with smtplib.SMTP(smtp_server, smtp_port) as server: 
            server.starttls() 
            server.login(sender, password) 
            server.send_message(msg) 
        print("✅ Email sent to", recipient) 
    except Exception as e: 
        print("❌ Failed to send email:", e) 
  
def schedule_email(): 
    schedule.every(5).minutes.do(send_email) 
    threading.Thread(target=schedule_runner, daemon=True).start() 
  
def schedule_runner(): 
    while True: 
        schedule.run_pending() 
        time.sleep(60) 
  
# --- Slack Interaction --- 
  
def send_region_selector(say, action_type): 
    say( 
        blocks=[ 
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🌎 *Select 
region for {action_type.upper()}*"}}, 
            { 
                "type": "actions", 
 "elements": [ 
                    {"type": "button", "text": {"type": "plain_text", "text": 
region}, "action_id": f"{action_type}_{region.replace('-', '_')}"} 
                    for region in REGION_OPTIONS 
                ] 
            } 
        ] 
    ) 
  
@app.message("^menu$") 
def show_menu(message, say): 
    blocks = [ 
        {"type": "section", "text": {"type": "mrkdwn", "text": "👋 *Choose an AWS 
action:*"}}, 
        {"type": "actions", "elements": [ 
            {"type": "button", "text": {"type": "plain_text", "text": "List S3"}, 
"action_id": "list_s3"}, 
            {"type": "button", "text": {"type": "plain_text", "text": "List EC2"}, 
"action_id": "list_ec2"}, 
            {"type": "button", "text": {"type": "plain_text", "text": "List VPC"}, 
"action_id": "list_vpc"}, 
        ]}, 
        {"type": "actions", "elements": [ 
            {"type": "button", "text": {"type": "plain_text", "text": "List NAT GW"}, 
"action_id": "list_nat"}, 
            {"type": "button", "text": {"type": "plain_text", "text": "List EKS"}, 
"action_id": "list_eks"}, 
            {"type": "button", "text": {"type": "plain_text", "text": "List ECR"}, 
"action_id": "list_ecr"}, 
        ]}, 
        {"type": "actions", "elements": [ 
            {"type": "button", "text": {"type": "plain_text", "text": "Billing 
(Monthly)"}, "action_id": "billing_monthly"}, 
            {"type": "button", "text": {"type": "plain_text", "text": "Billing 
(Weekly)"}, "action_id": "billing_weekly"}, 
        ]}, 
        {"type": "actions", "elements": [ 
            {"type": "button", "text": {"type": "plain_text", "text": "High Cost 
Resource"}, "action_id": "high_cost"}, 
        ]} 
    ] 
    say(blocks=blocks) 
  
# Main menu buttons handlers 
@app.action("list_s3") 
def handle_list_s3(ack, say): 
    ack() 
    say(list_s3_buckets()) 
  
@app.action("list_ec2") 
def handle_list_ec2(ack, say): 
    ack() 
    send_region_selector(say, "ec2")
@app.action("list_vpc") 
def handle_list_vpc(ack, say): 
    ack() 
    send_region_selector(say, "vpc") 
  
@app.action("list_nat") 
def handle_list_nat(ack, say): 
    ack() 
    send_region_selector(say, "nat") 
  
@app.action("list_eks") 
def handle_list_eks(ack, say): 
    ack() 
    send_region_selector(say, "eks") 
  
@app.action("list_ecr") 
def handle_list_ecr(ack, say): 
    ack() 
    send_region_selector(say, "ecr") 
  
@app.action("billing_monthly") 
def handle_billing_monthly(ack, say): 
    ack() 
    say(get_aws_billing("monthly")) 
  
@app.action("billing_weekly") 
def handle_billing_weekly(ack, say): 
    ack() 
    say(get_aws_billing("weekly")) 
  
@app.action("high_cost") 
def handle_high_cost(ack, say): 
    ack() 
    say(get_high_cost_resources()) 
  
# Dynamic region action handlers generator 
for service in ["ec2", "vpc", "nat", "eks", "ecr"]: 
    for region in REGION_OPTIONS: 
        action_id = f"{service}_{region.replace('-', '_')}" 
        region_code = region 
  
        # Define handler closure to bind parameters correctly 
        def make_handler(action_id, service, region_code): 
            @app.action(action_id) 
            def handler(ack, say): 
                ack() 
                try: 
                    if service == "ec2": 
                        say(list_ec2_instances(region_code)) 
                    elif service == "vpc": 
                        say(list_vpcs(region_code)) 
                    elif service == "nat": 
                        say(list_nat_gateways(region_code)) 
                    elif service == "eks": 
 say(list_eks_clusters(region_code)) 
                    elif service == "ecr": 
                        say(list_ecr_repositories(region_code)) 
                except Exception as e: 
                    say(f"🚨 Error processing {service.upper()} in {region_code}: 
{e}") 
            return handler 
        make_handler(action_id, service, region_code) 
  
# GPT fallback handler 
@app.message(".*") 
def fallback_handler(message, say): 
    text = message['text'].strip() 
    if text.lower() == "menu": 
        return  # ignore, menu handled above 
    try: 
        output = chatgpt_chain.predict(human_input=text) 
        say(output) 
    except Exception as e: 
        say(f"🤖 GPT Error: {e}") 
  
# --- Run everything --- 
  
if __name__ == "__main__": 
    schedule_email() 
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]) 
    handler.start()
