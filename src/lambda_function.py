'''
Lambda function for Lex bot to point DNS names to other loadbalancers.
CodeHook for Scotty bot to handle user validation, slot/card creation and routing to new load balancer. 
'''

import time
import os
import logging
import boto3
import json
from botocore.vendored import requests

logger = logging.getLogger()
logger.setLevel(logging.CRITICAL)

""" --- Helpers to build responses which match the structure of the necessary dialog actions --- """


def get_slots(intent_request):
    return intent_request['currentIntent']['slots']
    

def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message, response_card):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ElicitSlot',
            'intentName': intent_name,
            'slots': slots,
            'slotToElicit': slot_to_elicit,
            'message': message,
            'responseCard': response_card
        }
    }


def close(session_attributes, fulfillment_state, message):
    response = {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': message
        }
    }

    return response


def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }
    
    
def build_response_card(title, subtitle, options):
    if len(options)<=5:
        buttons = None
        if options is not None:
            buttons = []
            for i in range(min(5, len(options))):
                buttons.append(options[i])
        return {'contentType': 'application/vnd.amazonaws.card.generic',
                'version': 1,
                'genericAttachments': [{
                    'title': title,
                    'subTitle': subtitle,
                    'buttons': buttons
                    }]
                }

    if not title:
        title = ' '

    genericAttachments = None

    if options is not None:
        genericAttachments = []
        N = 5
        # break down the list of options into a list of sub lists of length 5, slack limit is 5
        subList = [options[n:n + N] for n in range(0, len(options), N)]
        # For each sublist, create an attachment dict and append it to genericAttachments
        for i in range(0, len(subList)):
            attachment = {}
            attachment['title'] = title
            attachment['buttons'] = subList[i]
            if subtitle:
                attachment['subTitle'] = subtitle
            genericAttachments.append(attachment)

    response_card = {}
    response_card['contentType'] = 'application/vnd.amazonaws.card.generic'
    response_card['version'] = 1
    response_card['genericAttachments'] = genericAttachments
    return response_card


def operations(intent_request):
    output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
    userid=intent_request.get('userId')  #third portion is the slack user id, second is the slack team id
    with open('config.json') as data_file:    
            config = json.load(data_file)
    if output_session_attributes == {}:
        logger.critical('output_session_attributes empty')
        users=config.get('Authentication')
        userIDs=list(users.values())
        if userid == '': #id in lex test console 
            output_session_attributes['is_authorized_user']='True'
        else:
            ids=userid.split(':')
            try: #for testing in aws console
                userid=ids[2]
                logger.critical('userid'+userid)
                if userid in userIDs:
                    output_session_attributes['is_authorized_user']='True'
                    for user in users:
                        if users.get(user) == userid:
                            validateduser=users.get(user)
                            output_session_attributes['slackusername']= user
                            break
                else:
                    intent_request['sessionAttributes']['is_authorized_user']='False'
            except Exception:
                pass

    # if (output_session_attributes.get('is_authorized_user') is None) or ('True' not  in (output_session_attributes.get('is_authorized_user')) ) :  #intentrequest holds strings
    #     return close({}, 
    #              'Fulfilled',
    #              {'contentType': 'PlainText',
    #              'content': 'You must be a valid user to use this bot. ' })
 
    application_name = intent_request['currentIntent']['slots']['Application']
    environment_name = intent_request['currentIntent']['slots']['Environment']
    reason = intent_request['currentIntent']['slots']['Reason']
    confirm = intent_request['currentIntent']['slots']['Confirmation']

    #application_name=None #test: if not application_name:
    #environment_name=None #test: if application_name and not environment_name:
    source = intent_request['invocationSource']

    if source == 'DialogCodeHook':
        slots = intent_request['currentIntent']['slots']

        if not application_name:
           
            client = boto3.client('elasticbeanstalk', region_name='us-east-1') #update to handle multi env
            response = client.describe_applications( )
            card=[]
            slot=[]
            for app in response.get('Applications'):
                card.append( {'text': app.get('ApplicationName'), 'value': app.get('ApplicationName') }     )
                slot.append( { 'value': app.get('ApplicationName')  } )
            update_slot_type('EbApplication','$LATEST', slot)
            
            return elicit_slot(
                output_session_attributes,
                intent_request['currentIntent']['name'],
                intent_request['currentIntent']['slots'],
                'Application',
                {'contentType': 'PlainText', 'content': 'Application to switch?' }, #+str(userid) +str(validateduser)
                build_response_card('', '', card)
            )
            
        if application_name and not environment_name:
            try:
                with open('config.json') as data_file:    
                    config = json.load(data_file).get('Applications')
                    
                for region in config:
                    for app in config.get(region):
                        if app.get('ApplicationName') == application_name:
                            output_session_attributes['region']=region
                            break
                    break
                client = boto3.client('elasticbeanstalk',  region_name=output_session_attributes.get('region'))
                response = client.describe_environments(ApplicationName=application_name)
                card=[]
                slot=[]
                for env in response.get('Environments'):
                    card.append( {'text': env.get('EnvironmentName'), 'value': env.get('EnvironmentName')}     )
                    slot.append( { 'value': env.get('EnvironmentName')  } )
                logging.critical(slot)
    
                with open('config.json') as data_file:    
                    config = json.load(data_file).get('Applications')
    
                running_env = get_hostedzone_balancers(config, application_name,intent_request)
                
                update_slot_type('ApplicationEnvironment','$LATEST', slot)  
                
                for pos,card_slot in enumerate(card):
                    if card_slot.get('value') == running_env:
                        del card[pos]
                        break
            except Exception as e:
                return close({}, 
                     'Fulfilled',
                     {'contentType': 'PlainText',
                     'content': 'Exception '+e.format(environment_name, application_name)})
                     
            return elicit_slot(
                output_session_attributes,
                intent_request['currentIntent']['name'],
                intent_request['currentIntent']['slots'],
                'Environment',
                {'contentType': 'PlainText', 'content': 'What environment would you like to switch to?'+str(application_name)},
                build_response_card('Currently running on ' + running_env , 'Pick environment to run on' , card ) 
                )
      
    if source == 'FulfillmentCodeHook':
        
        if confirm == 'no':
            return close({}, 
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Ok nothing was done'})
        else:
            intent_request['sessionAttributes']['newTarget']=get_new_lb_target(output_session_attributes, environment_name)
            newtarget=intent_request['sessionAttributes']['newTarget'] 
            
            with open('config.json') as data_file:   
                data = json.load(data_file)
            config=data.get('Applications')
            url=data.get('SlackUrl')
            for zone in config:
                for app in config.get(zone):
                    if app.get('ApplicationName') == application_name:
                        client = boto3.client('route53')
                        response = client.change_resource_record_sets(
                            HostedZoneId = app.get('HostedZoneId'),
                            ChangeBatch = {
                                'Changes': [
                                    {
                                        'Action':  'UPSERT', 
                                        'ResourceRecordSet': {
                                            'Name': app.get('DNSRecord'),  
                                            'Type': 'A',  
                                            'AliasTarget': {   
                                                'HostedZoneId': intent_request['sessionAttributes']['recordHostedZone'],  
                                                'DNSName': newtarget, 
                                                'EvaluateTargetHealth':  False
                                            },
                                        }
                                    },
                                ]
                            }
                        )
                        break
            if response.get('ResponseMetadata').get('HTTPStatusCode') == 200:
                data = "{\"text\": \" Success in switching the live environment for *"+application_name+"* to *"+environment_name+"* by *"+output_session_attributes.get('slackusername')+"* (Reason:"+reason+")  \", \"channel\": \"#prod-deployments\", \"link_names\": 1, \"username\": \"Scotty\", }"
                requests.post(url, headers={'Content-type': 'application/json'}, data=data)
                data = "{\"text\": \" Success in switching the live environment for *"+application_name+"* to *"+environment_name+"* by *"+output_session_attributes.get('slackusername')+"* (Reason:"+reason+")  \", \"channel\": \"#team-devops\", \"link_names\": 1, \"username\": \"Scotty\", }"
                requests.post(url, headers={'Content-type': 'application/json'}, data=data)
                
                
                return close({}, 
                     'Fulfilled',
                     {'contentType': 'PlainText',
                     'content': 'We rotated to {} for application {}. '.format(environment_name, application_name)})
            else:
                return close({}, 
                     'Fulfilled',
                     {'contentType': 'PlainText',
                      'content': 'change_resource_record_sets failed'})
            
    return delegate(output_session_attributes, slots)
 

def update_slot_type(slot_type_name, slot_type_version, slot ):
    
    lexclient = boto3.client('lex-models')
    oldinstance = lexclient.get_slot_type(
                    name=slot_type_name,
                    version=slot_type_version #string
                    )
    response = lexclient.put_slot_type(
                    name=slot_type_name,
                    enumerationValues=slot,
                    checksum=oldinstance.get('checksum'),
                    createVersion=False
                    )
 
                    
def get_hostedzone_balancers(config, appname,intent_request):
    client = boto3.client('route53')
    # get loadbalancer from route 53 with hostedzone id and appname
    for zone in config:
        region= zone
        for app in config.get(zone):
            if app.get('ApplicationName') == appname:
                response = client.list_resource_record_sets(HostedZoneId=app.get('HostedZoneId'),StartRecordName=app.get('DNSRecord'),MaxItems='1') 
                loadbalancerdns=(response.get('ResourceRecordSets')[0].get('AliasTarget').get('DNSName'))
                intent_request['sessionAttributes']['recordHostedZone']= (response.get('ResourceRecordSets')[0].get('AliasTarget').get('HostedZoneId'))
                break
        break
    intent_request['sessionAttributes']['region']=region  
    
    return get_running_env(region, loadbalancerdns)  
    

def get_running_env(region, loadbalancerdns) : 
    client = boto3.client('elb', region_name=region) 
    logger.critical(region)
    paginator = client.get_paginator('describe_load_balancers')
    page_iterator = paginator.paginate()
    for page in page_iterator:
        for loadbalancer in page.get('LoadBalancerDescriptions'):
            #logger.critical(loadbalancer.get('DNSName').lower())
            if loadbalancer.get('DNSName').lower() in loadbalancerdns:
                tagresponse = client.describe_tags(LoadBalancerNames=[loadbalancer.get('LoadBalancerName')])
                tags = tagresponse.get('TagDescriptions')[0].get('Tags')
                for tag in tags:
                    if tag.get('Key') == 'elasticbeanstalk:environment-name':
                        logger.critical(tag.get('Value'))
                        return tag.get('Value') #environment-name
                    

def get_new_lb_target(output_session_attributes, environment_name):
    client = boto3.client('elb', region_name=output_session_attributes.get('region'))
    response = client.describe_load_balancers()
    for loadbalancer in response.get('LoadBalancerDescriptions'):
        tagresponse = client.describe_tags(LoadBalancerNames=[loadbalancer.get('LoadBalancerName')])
        tags = tagresponse.get('TagDescriptions')[0].get('Tags')
        for tag in tags:
            if tag.get('Value') == environment_name:  # SLOT ENVIRONMENT
                return loadbalancer.get('DNSName')
                
#ENTRY POINT
def dispatch(intent_request):
  
    intent_name = intent_request['currentIntent']['name']
    if intent_name == 'LBswitcher':
        return operations(intent_request)
    raise Exception('Intent with name ' + intent_name + ' not supported')


""" --- Main handler --- """

def lambda_handler(event, context):
   
    os.environ['TZ'] = 'America/New_York'
    time.tzset()
    logger.debug('event.bot.name={}'.format(event['bot']['name']))

    return dispatch(event)
