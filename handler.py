import datetime
import json
import os
import requests
import time
import logging
import sys
import pandas as pd
import boto3
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def send_email(event, customerInfo, orderInfo):
    SENDER = "campagnarodhonatan20@gmail.com"
    RECIPIENT = "tobypilling@gmail.com"
    recipients = ["tobypilling@gmail.com", "falk.jaehnchen@hotspex.com"]
    CONFIGURATION_SET = "order"
    SUBJECT = "Order"
    BODY_TEXT = "OrderInfo\r\n\n" \
                "Posted data from Shopify:\n\n{}\n\n\n" \
                "Customer:\n\n{}\n\n\nOrderInfo:\n\n{}\n".format(json.dumps(event),
                                                                      customerInfo, orderInfo)

    CHARSET = "utf-8"

    client = boto3.client('ses', region_name=os.environ['REGION'],
                          aws_access_key_id=os.environ['ACCESS_KEY_ID'],
                          aws_secret_access_key=os.environ['SECRET_ACCESS_KEY'])

    msg = MIMEMultipart('mixed')
    msg['Subject'] = SUBJECT
    msg['From'] = SENDER
    msg['To'] = RECIPIENT

    msg_body = MIMEMultipart('alternative')
    textpart = MIMEText(BODY_TEXT.encode(CHARSET), 'plain', CHARSET)

    msg_body.attach(textpart)

    msg.attach(msg_body)

    try:
        response = client.send_raw_email(
            Source=SENDER,
            Destinations=recipients,
            RawMessage={
                'Data': msg.as_string(),
            },
            ConfigurationSetName=CONFIGURATION_SET
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])


def get_fIds(pId):
    bucket = "immuno4ce"
    file_name = "maps.json"
    s3 = boto3.client('s3', region_name=os.environ['REGION'],
                      aws_access_key_id=os.environ['ACCESS_KEY_ID'],
                      aws_secret_access_key=os.environ['SECRET_ACCESS_KEY'])
    obj = s3.get_object(Bucket=bucket, Key=file_name)
    initial_df = pd.read_json(obj['Body'])
    out = initial_df.to_json(orient='records')
    for maps in json.loads(out):
        if maps["maps"]["pId"] == pId:
            return maps["maps"]["fIds"]
    return None


def findOrderId(orderId, cust_info):
    endpoint = "https://api-sandbox.okcapsule.com/v1/orders"
    headers = {
        "X-User": os.environ['OKCAPSULE_USER_ID'],
        "Authorization": "apikey {}".format(os.environ['OKCAPSULE_API_KEY']),
        "Content-Type": "application/json"
    }
    result = requests.get(endpoint, headers=headers, timeout=30)

    tmp = json.loads(result.text)
    recordId = ''
    for item in tmp["results"]:
        if orderId == item["clientOrderId"]:
            recordId = item["recordId"]
            break
    endpoint = "https://api-sandbox.okcapsule.com/v1/orders?recordId={}".format(recordId)
    data_json = {
                  "shipToAccountId": cust_info["customerAccountId"],
                  "shippingStreet": cust_info["shippingStreet"],
                  "shippingState": cust_info["shippingState"],
                  "shippingPostalCode": cust_info["shippingPostalCode"],
                  "shippingCountry": cust_info["shippingCountry"],
                  "shippingCity": cust_info["shippingCity"],
                  "customerShippingContactEmail": cust_info["email"],
                  "clientId": cust_info["clientAccountId"],
                }
    result = requests.put(endpoint, headers=headers, data=json.dumps(data_json), timeout=30)

    logger.warning(result.text)
    return json.loads(result.text)


def delete_orderLines():
    endpoint = "https://api-sandbox.okcapsule.com/v1/orderlines"
    headers = {
        "X-User": os.environ['OKCAPSULE_USER_ID'],
        "Authorization": "apikey {}".format(os.environ['OKCAPSULE_API_KEY']),
        "Content-Type": "application/json"
    }
    result = requests.get(endpoint, headers=headers, timeout=30)

    tmp = json.loads(result.text)

    for item in tmp["results"]:
        recordId = item["recordId"]
        rst = requests.delete('https://api-sandbox.okcapsule.com/v1/orderlines?recordId={}'.format(recordId), headers=headers, timeout=30)
        logger.warning(recordId, rst.text)


def create_orderLines(fIdsAry, orderId, customerInfo_json):
    data_encoded = []
    result = create_order(orderId, customerInfo_json)
    recordId = ''
    record = {}
    try:
        recordId = result['recordId']
    except Exception as e:
        record = findOrderId(orderId, customerInfo_json)
        logger.warning(record)
        recordId = record["recordId"]
    logger.warning(recordId)

    for fIds in fIdsAry:
        for fId in fIds:
            salesOrder = {
                "salesOrderId": recordId,
                "formularyId": fId["id"],
                "servingSizeNumber": fId["ssn"],
                "timeOfAdministration": fId["toa"]
            }
            data_encoded.append(salesOrder)
    endpoint = "https://api-sandbox.okcapsule.com/v1/orderlines"
    headers = {
        "X-User": os.environ['OKCAPSULE_USER_ID'],
        "Authorization": "apikey {}".format(os.environ['OKCAPSULE_API_KEY']),
        "Content-Type": "application/json"
    }
    orderlines = requests.post(endpoint, headers=headers, data=json.dumps(data_encoded), timeout=30)
    if result.status_code == 400:
        return {'order': record,
                'orderlines': orderlines.text}
    return {'order': result.text,
            'orderlines': orderlines.text}


def create_order(id, customerInfo_json):
    shipToAccountId = customerInfo_json["customerAccountId"]
    endpoint = "https://api-sandbox.okcapsule.com/v1/orders"
    headers = {
        "X-User": os.environ['OKCAPSULE_USER_ID'],
        "Authorization": "apikey {}".format(os.environ['OKCAPSULE_API_KEY']),
        "Content-Type": "application/json"
    }
    data_encoded = {
        "shipToAccountId": str(shipToAccountId),
        "orderType": "DTC",
        "duration": "30",
        "clientOrderId": str(id),
        "brandId": "a012f000002rRtoAAE",
        "shippingStreet": customerInfo_json["shippingStreet"],
        "shippingState": customerInfo_json["shippingState"],
        "shippingPostalCode": customerInfo_json["shippingPostalCode"],
        "shippingCountry": customerInfo_json["shippingCountry"],
        "shippingCity": customerInfo_json["shippingCity"],
        "customerShippingContactEmail": customerInfo_json["email"],
        "clientId": customerInfo_json["clientAccountId"],

    }
    response = requests.post(endpoint, headers=headers, data=json.dumps(data_encoded), timeout=30)
    return response


def checkCustomerInfo(customer, shipping_address):
    data_encoded = {
                        "lastName": customer["last_name"],
                        "firstName": customer["first_name"],
                        "email": customer["email"],
                        "clientAccountId": str(customer["id"]),
                        "shippingPostalCode": shipping_address["zip"],
                        "shippingStreet": shipping_address["address1"],
                        "shippingState": shipping_address["province"],
                        "shippingCountry": shipping_address["country"],
                        "shippingContact": '',
                        "shippingCity": shipping_address["city"],
                        "phone": shipping_address["phone"],
                        "clientCustomerId": str(customer["default_address"]["customer_id"])
                    }

    endpoint = "https://api-sandbox.okcapsule.com/v1/customers"

    headers = {
        "X-User": os.environ['OKCAPSULE_USER_ID'],
        "Authorization": "apikey {}".format(os.environ['OKCAPSULE_API_KEY']),
        "Content-Type": "application/json"
    }
    recordId = ""
    response_data = ''
    try:
        response_data = requests.post(endpoint, headers=headers, data=json.dumps(data_encoded), timeout=30)
    except Exception as e:
        logger.warning(e)

    if response_data.status_code == 400:
        all_customers = requests.get(endpoint, headers=headers, timeout=30)
        all_customers_list = json.loads(all_customers.text)
        for item in all_customers_list["results"]:
            if data_encoded["clientCustomerId"] == item["clientCustomerId"]:
                recordId = str(item["recordId"])
                break
        data_encoded.pop('clientAccountId')
        data_encoded.pop('clientCustomerId')
        update_endpoint = "https://api-sandbox.okcapsule.com/v1/customers?recordId={}".format(recordId)
        response_data = requests.put(update_endpoint, headers=headers, data=json.dumps(data_encoded), timeout=30)
        logger.warning(response_data.text)

    return response_data.text


def main(event, line_items, customer, shipping_address):
    customerInfo = checkCustomerInfo(customer, shipping_address)
    customerInfo_json = json.loads(customerInfo)
    orderInfo = []
    for line_item in line_items:
        orderId = str(event['id'])
        pId = line_item['product_id']
        quantity = line_item['quantity']
        fIds = []
        for iCnt in range(int(quantity)):
            fId = get_fIds(str(pId))
            fIds.append(fId)
        response = create_orderLines(fIds, str(orderId), customerInfo_json)
        response["fIds"] = fIds
        orderInfo.append(response)

    send_email(event, customerInfo, orderInfo)
    return 200


def handler(event, context):
    try:
        now = datetime.datetime.now()
        current_time = now.strftime("%d/%m/%Y %H:%M:%S")
        print("Started at =", current_time)

        response = main(event, event["line_items"], event["customer"], event["shipping_address"])

        now = datetime.datetime.now()
        current_time = now.strftime("%d/%m/%Y %H:%M:%S")
        print("Ended at =", current_time)
        return response
    except Exception as e:
        print(e)
        return None


if __name__ == "__main__":
    with open('config.json') as json_file:
        config = json.load(json_file)

    os.environ['REGION'] = config['REGION']
    os.environ['ACCESS_KEY_ID'] = config['ACCESS_KEY_ID']
    os.environ['SECRET_ACCESS_KEY'] = config['SECRET_ACCESS_KEY']
    os.environ['OKCAPSULE_API_KEY'] = config['OKCAPSULE_API_KEY']
    os.environ['OKCAPSULE_USER_ID'] = config['OKCAPSULE_USER_ID']

    try:
        now = datetime.datetime.now()
        current_time = now.strftime("%d/%m/%Y %H:%M:%S")
        print("Current Time =", current_time)

        with open('tmp.json') as tmp:
            event = json.load(tmp)
        main(event, event["line_items"], event["customer"], event["shipping_address"])

        now = datetime.datetime.now()
        current_time = now.strftime("%d/%m/%Y %H:%M:%S")
        print("Current Time =", current_time)
    except Exception as e:
        print(e)

    del os.environ['REGION']
    del os.environ['ACCESS_KEY_ID']
    del os.environ['SECRET_ACCESS_KEY']
    del os.environ['OKCAPSULE_API_KEY']
    del os.environ['OKCAPSULE_USER_ID']
