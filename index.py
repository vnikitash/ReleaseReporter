import json
import urllib 
import base64
from botocore.vendored import requests
import re
from datetime import datetime

JIRA_USER_LOGIN = "***";
JIRA_USER_TOKEN = "***";
GITHUB_USER_LOGIN = "***";
GITHUB_USER_TOKEN = "***";
JIRA_DONE_TRANSITION_ID = "***";
JIRA_DOMAIN = "***";
GITHUB_COMMIT_REGEX = "'( |\|)RR-[0-9]{1,}( |\|)'";

GITHUB_TO_SLACK_MAPPER = {
    "***": '@UBVXXXXX',
};

JIRA_TO_SLACK_MAPPER = {
    'jira.user@example.com': '@UBVXXXXX',
};

SLACK_CHANNELS = {
    'my-channel': 'https://hooks.slack.com/services/TBQXXXXXX/XXXXXXXXX/XXXXXXXXXXXXXXXXXXXXXXXX',
}

def lambda_handler(event, context):
    
    result = getInitialConfigs(event['queryStringParameters']);
    
    if result['status'] is False:
        return {
            'statusCode': 400,
            'body': json.dumps(result['body'])
        }
        
    configs = result['body'];
    tasks = getTasksFromCommits(configs['pr'], configs['vendor'], configs['repo']);
    report = proceedJIRAIssues(tasks);
    sendSlackReport(configs['from'], report, configs['channel']);
    
    return {
        'statusCode': 200,
        'body': json.dumps(report)
    }
    
def getInitialConfigs(params):
    
    if params is None:
        return {
            'status': False,
            'body': 'Required parameters `pr` and `channel` are missing.'
        }
    
    if 'pr' not in params:
        return {
            'status': False,
            'body': 'You should provide `pr` parameter'
        }
        
    if 'channel' not in params:
        return {
            'status': False,
            'body': 'You should provide `channel` parameter'
        }
    
    if params['channel'] not in SLACK_CHANNELS:
        return {
            'status': False,
            'body': 'The provided `channel` is incorrect'
        }
    
    if 'vendor' not in params:
        params['vendor'] = 'stryberventures';
    
    if 'repo' not in params:
        params['repo'] = 'RoadRunnerPhpApi';
        
    if 'from' not in params:
        params['from'] = 'local';
        
    return {
        'status': True,
        'body': {
            'pr': params['pr'],
            'channel': params['channel'],
            'vendor': params['vendor'],
            'repo': params['repo'],
            'from': params['from']
        }
    }
        

def getTasksFromCommits(pr, vendor, repo):
    
    githubCommitsUrl = "https://api.github.com/repos/" + vendor + "/" + repo + "/pulls/" + pr + "/commits";
    requestHeaders = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36'};
    res = requests.get(githubCommitsUrl, headers=requestHeaders, auth=(GITHUB_USER_LOGIN, GITHUB_USER_TOKEN));
    commits = json.loads(res.text);
    
    tasks = [];
    for commit in commits:
        tasks.append({
            'user': commit['commit']['author']['name'],
            'message': commit['commit']['message']
        });
    
    groupedTasks = {};
    
    for task in tasks:
        output = re.search(GITHUB_COMMIT_REGEX, task['message'], flags=re.IGNORECASE)
        if output is not None:
            groupedTasks[output.group(0).strip()] = task['user'];
            
    return groupedTasks;
    
def proceedJIRAIssues(tasks):
 
    jiraTicketsInfo = [];
    for taskNumber in tasks:
        jiraTicketsInfo.append(getJIRATaskInformation(tasks[taskNumber], taskNumber))
        setJIRATaskToDone(taskNumber)
        commentJIRATask(taskNumber)
        
    return jiraTicketsInfo;
    
def getJIRATaskInformation(taskExecutive, taskNumber):

    jiraTicketsInfoUrl = "https://" + JIRA_DOMAIN + ".atlassian.net/rest/api/3/issue/" + taskNumber;
    requestHeaders = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36'};
    res = requests.get(jiraTicketsInfoUrl, headers=requestHeaders, auth=(JIRA_USER_LOGIN, JIRA_USER_TOKEN));
    result = json.loads(res.text);

    if taskExecutive in GITHUB_TO_SLACK_MAPPER:
        taskExecutive = GITHUB_TO_SLACK_MAPPER[taskExecutive]
    
    reporter = result['fields']['reporter']['emailAddress'];
    
    if reporter in JIRA_TO_SLACK_MAPPER:
        reporter = JIRA_TO_SLACK_MAPPER[reporter];
    
    return {
        'executor': taskExecutive,
        'link': "https://" + JIRA_DOMAIN + ".atlassian.net/browse/" + taskNumber,
        'title': result['fields']['summary'],
        'reporter': reporter
    }
    
def setJIRATaskToDone(ticketNumber):
    
    body = {"transition": {"id": JIRA_DONE_TRANSITION_ID}};
    jiraTicketsChangeTransitionUrl = "https://" + JIRA_DOMAIN + ".atlassian.net/rest/api/3/issue/" + ticketNumber + "/transitions";
    requestHeaders = {'User-Agent': JIRA_DOMAIN, "Content-Type": "application/json"};
    res = requests.post(jiraTicketsChangeTransitionUrl, headers=requestHeaders, auth=(JIRA_USER_LOGIN, JIRA_USER_TOKEN), json=body);
    
def commentJIRATask(taskNumber):

    body = {
    	"body": {
    	    "type": "doc",
    	    "version": 1,
    	    "content": [
    	        {
        	        "type": "paragraph",
        	        "content": [
        	            {
            	            "type": "text",
            	            "text": "Task has beed deployed on production at " + f'{datetime.now():%Y-%m-%d %H:%M:%S%z}' + " (UTC+0)"
            	        }
    	            ]
    	        }
    	    ]
        }
    };

    jiraTicketsCommentsUrl = "https://" + JIRA_DOMAIN + ".atlassian.net/rest/api/3/issue/" + taskNumber + "/comment";
    requestHeaders = {'User-Agent': JIRA_DOMAIN, "Content-Type": "application/json"};
    requests.post(jiraTicketsCommentsUrl, headers=requestHeaders, auth=(JIRA_USER_LOGIN, JIRA_USER_TOKEN), json=body);
    
    
def sendSlackReport(env, tasks, slackChannel):
    
    output = "`" + env + "` build started at: " + f'{datetime.now():%Y-%m-%d %H:%M:%S%z}' + " (UTC+0)";
    
    index = 0;
    for task in tasks:
        index = index + 1;
        output = output + "\n\n";
        output = output + str(index) + ') ' + task['title'] + "\n" + 'Link: ' + task['link'] + "\n" + 'Reporter: <' + task['reporter'] + '>' + "\n" + 'Executor: <' + task['executor'] + '>';

    body = {
        'text': output,
        'link_names': 1
    };
    slackWebhookUrl = SLACK_CHANNELS[slackChannel];
    requestHeaders = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36',
        "Content-Type": "application/json"
    };
    requests.post(slackWebhookUrl, headers=requestHeaders, auth=(JIRA_USER_LOGIN, JIRA_USER_TOKEN), json=body);