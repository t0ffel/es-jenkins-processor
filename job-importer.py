import argparse
import datetime
import os

import elasticsearch

# host => "ops-qe-logstash-2.rhev-ci-vms.eng.rdu2.redhat.com"
#    port => "9200"
#    index => "rhci-logstash-%{+YYYY.MM.dd}"

def get_matches(build_id, index_base, query_size, debug=False, numdays=14):
    full_url = jenkins_url + "/job/" + jenkins_job + "/" + build_id + "/"
    query = {
         "filter": {
             "term": {
                "fields.full_url.raw": full_url
             }
         }
    }


#'fields.url:"%s"' %build_id
    index_list = []
    base = datetime.datetime.today()
    date_list = [base - datetime.timedelta(days=x) for x in range(0, numdays)]
    for date in date_list:
        index_value = "rhci-logstash-%s" %(str(date).split(' ')[0].replace('-','.'))
        if indices.exists(index_value):
            index_list.append(index_value)
    
    matches = es.search(index_list, body=query, size=query_size, explain=True)
    if debug:
        print "Matches for: query: %s | index:  %s |  query_size: %s" %(query, index_list, query_size)
        #print matches
        print '-'*80
    return matches

def get_messages(matches):
    hits = matches['hits']['hits']
    messages = [x['_source']['message'] for x in hits]
    if debug:
        print "Messages found: "
        print messages
        for message in messages:
            print message
        print '#'*80
    return messages

def get_job_timestamps(matches):
    """get job metadata from the list of individual log entries: job_start, job_end"""
    hits = sorted(matches['hits']['hits'],key=lambda hit: hit['_source']['@timestamp'])
    return (hits[0]['_source']['@timestamp'],hits[-1]['_source']['@timestamp'])
    

def get_job_size(matches):
    return matches['hits']['total']

def get_job_details(matches):
    """derive the details from sample log entry: full_url, jenkins_master, build_number, phase, status, tags, job_name"""
    hit = matches['hits']['hits'][0]['_source']

    job_body = {
             "build_number":     hit['fields']['number'],
             "jenkins_master":   "",
             "phase":            hit['fields']['phase'],
             "status":           hit['fields']['status'],
             "tags":             hit['tags'],
             "full_url":         hit['fields']['full_url'],
             "job_name":         hit['job_name']
           }
    return job_body

def diff_messages(build1, build2, messages1, messages2, debug=False):
    print "Diff of %s and %s:" %(build1, build2)
    diff = set(messages1)-set(messages2)
    if debug:
        print "Raw data: %s" %diff
    print '-'*80
    for line in diff:
        print line
        print '-'*80
    print '='*80

def publish_job(body):
    query = {
         "filter": {
             "term": {
                "full_url.raw": body['full_url']
             }
         }
    }
    existing_jobs = es_out.search(body=query, index=index_out, size=10)
    print "searching with query %s, on index %s" % (query, index_out)
    if existing_jobs['hits']['total'] == 0:
        print "Adding job to the elasticsearch"
        res = es_out.create(index=index_out, doc_type="jenkins_job", body=body, refresh=True)
        return res
    print "Job with full_url '%s' already exists in the jobs index %s" %(body['full_url'], index_out)

es_server = os.getenv('ELASTICSEARCH_SERVER')
es = elasticsearch.Elasticsearch([es_server])
indices = elasticsearch.client.IndicesClient(es)

es_server_target = os.getenv('ELASTICSEARCH_SERVER_TARGET')
es_out = elasticsearch.Elasticsearch([es_server_target])

# If we have a BUILD_ID provided, we use that
# otherwise, we use last_build by default
jenkins_job = os.getenv('JENKINS_JOB_NAME')
jenkins_url = os.getenv('JENKINS_URL')
build_id = os.getenv('BUILD_ID')

print
print
print '#'*80
print "Analyzing Jenkins job: %s" %(jenkins_job)
print "Build: %s" %(build_id)

query_size = int(os.getenv('QUERY_SIZE'))
num_days = int(os.getenv('NUM_DAYS'))
index_base = os.getenv('BUILD_INDEX_NAME')
index_out = os.getenv('JOBS_INDEX_NAME')
debug = os.getenv('DEBUG')
if debug == 'True':
    debug = True
else:
    debug = False

base_matches = get_matches(build_id, index_base, query_size, debug, num_days)
#base_messages = get_messages(base_matches)

(job_start, job_end) = get_job_timestamps(base_matches)
print "job started at: %s, finished at %s" % (job_start, job_end)

body = get_job_details(base_matches)
body['job_start'] = job_start
body['job_end'] = job_end
body['size'] = get_job_size(base_matches)

publish_job(body)

#print "job details are %s" % (body)
