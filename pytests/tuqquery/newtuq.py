import logger
import json
import uuid
import copy
import math
import re

import testconstants
import datetime
import time
from datetime import date
from couchbase_helper.tuq_generators import TuqGenerators
from couchbase_helper.tuq_generators import JsonGenerator
from remote.remote_util import RemoteMachineShellConnection
from basetestcase import BaseTestCase
from couchbase_helper.documentgenerator import DocumentGenerator
from membase.api.exception import CBQError, ReadDocumentException
from membase.api.rest_client import RestConnection
from memcached.helper.data_helper import MemcachedClientHelper

class QueryTests(BaseTestCase):
    def setUp(self):
        if not self._testMethodName == 'suite_setUp':
            self.skip_buckets_handle = True
        super(QueryTests, self).setUp()
        self.version = self.input.param("cbq_version", "git_repo")
        if self.input.tuq_client and "client" in self.input.tuq_client:
            self.shell = RemoteMachineShellConnection(self.input.tuq_client["client"])
        else:
            self.shell = RemoteMachineShellConnection(self.master)
        if not self._testMethodName == 'suite_setUp':
            self._start_command_line_query(self.master)
        self.use_rest = self.input.param("use_rest", True)
        self.max_verify = self.input.param("max_verify", None)
        self.buckets = RestConnection(self.master).get_buckets()
        self.docs_per_day = self.input.param("doc-per-day", 49)
        self.item_flag = self.input.param("item_flag", 4042322160)
        self.n1ql_port = self.input.param("n1ql_port", 8093)
        self.dataset = self.input.param("dataset", "default")
        self.gens_load = self.generate_docs(self.docs_per_day)
        if self.input.param("gomaxprocs", None):
            self.configure_gomaxprocs()
        self.gen_results = TuqGenerators(self.log, self.generate_full_docs_list(self.gens_load))
         # temporary for MB-12848
        self.create_primary_index_for_3_0_and_greater()

    def suite_setUp(self):
        try:
            self.load(self.gens_load, flag=self.item_flag)
            self.create_primary_index_for_3_0_and_greater()
            if not self.input.param("skip_build_tuq", True):
                self._build_tuq(self.master)
            self.skip_buckets_handle = True
        except:
            self.log.error('SUITE SETUP FAILED')
            self.tearDown()

    def tearDown(self):
        if self._testMethodName == 'suite_tearDown':
            self.skip_buckets_handle = False
        super(QueryTests, self).tearDown()

    def suite_tearDown(self):
        if not self.input.param("skip_build_tuq", False):
            if hasattr(self, 'shell'):
                self.shell.execute_command("killall /tmp/tuq/cbq-engine")
                self.shell.execute_command("killall tuqtng")
                self.shell.disconnect()


##############################################################################################
#
#   SIMPLE CHECKS
##############################################################################################
    def test_simple_check(self):
        for bucket in self.buckets:
            query_template = 'FROM %s select $str0, $str1 ORDER BY $str0,$str1 ASC' % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_simple_negative_check(self):
        queries_errors = {'SELECT $str0 FROM {0} WHERE COUNT({0}.$str0)>3' :
                          'Aggregates not allowed in WHERE',
                          'SELECT *.$str0 FROM {0}' : 'syntax error',
                          'SELECT *.* FROM {0} ... ERROR' : 'syntax error',
                          'FROM %s SELECT $str0 WHERE id=null' : 'syntax error',}
        self.negative_common_body(queries_errors)

    def test_consistent_simple_check(self):
        queries = [self.gen_results.generate_query('SELECT $str0, $int0, $int1 FROM %s ' +\
                    'WHERE $str0 IS NOT NULL AND $int0<10 ' +\
                    'OR $int1 = 6 ORDER BY $int0, $int1'),
                   self.gen_results.generate_query('SELECT $str0, $int0, $int1 FROM %s ' +\
                    'WHERE $int1 = 6 OR $str0 IS NOT NULL AND ' +\
                    '$int0<10 ORDER BY $int0, $int1')]
        for bucket in self.buckets:
            actual_result1 = self.run_cbq_query(queries[0] % bucket.name)
            actual_result2 = self.run_cbq_query(queries[1] % bucket.name)
            self.assertTrue(actual_result1['results'] == actual_result2['results'],
                              "Results are inconsistent.Difference: %s %s %s %s" %(
                                    len(actual_result1['results']), len(actual_result2['results']),
                                    actual_result1['results'][:100], actual_result2['results'][:100]))

    def test_simple_nulls(self):
        queries = ['SELECT id FROM %s WHERE id=NULL or id="null"']
        for bucket in self.buckets:
            for query in queries:
                actual_result = self.run_cbq_query(query % (bucket.name))
                self._verify_results(actual_result['results'], [])

##############################################################################################
#
#   LIMIT OFFSET CHECKS
##############################################################################################

    def test_limit_offset(self):
        for bucket in self.buckets:
            query_template = 'SELECT DISTINCT $str0 FROM %s ORDER BY $str0 LIMIT 10' % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)
            query_template = 'SELECT DISTINCT $str0 FROM %s ORDER BY $str0 LIMIT 10 OFFSET 10' % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)

    def test_limit_offset_zero(self):
        for bucket in self.buckets:
            query_template = 'SELECT DISTINCT $str0 FROM %s ORDER BY $str0 LIMIT 0' % (bucket.name)
            self.query = self.gen_results.generate_query(query_template)
            actual_result = self.run_cbq_query()
            self.assertEquals(actual_result['results'], [],
                              "Results are incorrect.Actual %s.\n Expected: %s.\n" % (
                                        actual_result['results'], []))
            query_template = 'SELECT DISTINCT $str0 FROM %s ORDER BY $str0 LIMIT 10 OFFSET 0' % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self.assertEquals(actual_result['results'], expected_result,
                              "Results are incorrect.Actual %s.\n Expected: %s.\n" % (
                                        actual_result['results'], expected_result))

    def test_limit_offset_negative_check(self):
        queries_errors = {'SELECT DISTINCT $str0 FROM {0} LIMIT -1' :
                          'Parse Error - syntax error',
                          'SELECT DISTINCT $str0 FROM {0} LIMIT 1.1' :
                          'Parse Error - syntax error',
                          'SELECT DISTINCT $str0 FROM {0} OFFSET -1' :
                          'Parse Error - syntax error',
                          'SELECT DISTINCT $str0 FROM {0} OFFSET 1.1' :
                          'Parse Error - syntax error'}
        self.negative_common_body(queries_errors)

##############################################################################################
#
#   ALIAS CHECKS
##############################################################################################

    def test_simple_alias(self):
        for bucket in self.buckets:
            query_template = 'SELECT COUNT($str0) AS COUNT_EMPLOYEE FROM %s' % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self.assertEquals(actual_result['results'], expected_result,
                              "Results are incorrect.Actual %s.\n Expected: %s.\n" % (
                                        actual_result['results'], expected_result))

            query_template = 'SELECT COUNT(*) + 1 AS COUNT_EMPLOYEE FROM %s' % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            expected_result = [ { "COUNT_EMPLOYEE": expected_result[0]['COUNT_EMPLOYEE'] + 1 } ]
            self.assertEquals(actual_result['results'], expected_result,
                              "Results are incorrect.Actual %s.\n Expected: %s.\n" % (
                                        actual_result['results'], expected_result))

    def test_simple_negative_alias(self):
        queries_errors = {'SELECT $str0._last_name as *' : 'syntax error',
                          'SELECT $str0._last_name as DATABASE ?' : 'syntax error',
                          'SELECT $str0 AS NULL FROM {0}' : 'syntax error',
                          'SELECT $str1 as $str0, $str0 FROM {0}' :
                                'Duplicate result alias name',
                          'SELECT test.$obj0 as points FROM {0} AS TEST ' +
                           'GROUP BY $obj0 AS GROUP_POINT' :
                                'syntax error'}
        self.negative_common_body(queries_errors)

    def test_alias_from_clause(self):
        queries_templates = ['SELECT $obj0.$_obj0_int0 AS points FROM %s AS test ORDER BY points',
                   'SELECT $obj0.$_obj0_int0 AS points FROM %s AS test WHERE test.$int0 >0'  +\
                   ' ORDER BY points',
                   'SELECT $obj0.$_obj0_int0 AS points FROM %s AS test ' +\
                   'GROUP BY test.$obj0.$_obj0_int0 ORDER BY points']
        for bucket in self.buckets:
            for query_template in queries_templates:
                actual_result, expected_result = self.run_query_from_template(query_template  % (bucket.name))
                self._verify_results(actual_result['results'], expected_result)

    def test_alias_from_clause_group(self):
        for bucket in self.buckets:
            query_template = 'SELECT $obj0.$_obj0_int0 AS points FROM %s AS test ' %(bucket.name) +\
                         'GROUP BY $obj0.$_obj0_int0 ORDER BY points'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_alias_order_desc(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str0 AS name_new FROM %s AS test ORDER BY name_new DESC' %(
                                                                                bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_alias_order_asc(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str0 AS name_new FROM %s AS test ORDER BY name_new ASC' %(
                                                                                bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_alias_aggr_fn(self):
        for bucket in self.buckets:
            query_template = 'SELECT COUNT(TEST.$str0) from %s AS TEST' %(bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_alias_unnest(self):
        for bucket in self.buckets:
            query_template = 'SELECT count(skill) FROM %s AS emp UNNEST emp.$list_str0 AS skill' %(
                                                                            bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

            query_template = 'SELECT count(skill) FROM %s AS emp UNNEST emp.$list_str0 skill' %(
                                                                            bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

##############################################################################################
#
#   ORDER BY CHECKS
##############################################################################################

    def test_order_by_check(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str0, $str1, $obj0.$_obj0_int0 points FROM %s'  % (bucket.name) +\
            ' ORDER BY $str1, $str0, $obj0.$_obj0_int0'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)
            query_template = 'SELECT $str0, $str1 FROM %s'  % (bucket.name) +\
            ' ORDER BY $obj0.$_obj0_int0, $str0, $str1'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_order_by_alias(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str1, $obj0 AS points FROM %s'  % (bucket.name) +\
            ' AS test ORDER BY $str1 DESC, points DESC'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_order_by_alias_arrays(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str1, $obj0, $list_str0[0] AS SKILL FROM %s'  % (
                                                                            bucket.name) +\
            ' AS TEST ORDER BY SKILL, $str1, TEST.$obj0'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_order_by_alias_aggr_fn(self):
        for bucket in self.buckets:
            query_template = 'SELECT $int0, $int1, count(*) AS emp_per_month from %s'% (
                                                                            bucket.name) +\
            ' WHERE $int1 >7 GROUP BY $int0, $int1 ORDER BY emp_per_month, $int1, $int0'  
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_order_by_aggr_fn(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str1 AS TITLE FROM %s GROUP'  % (bucket.name) +\
            ' BY $str1 ORDER BY MIN($int1), $str1'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_order_by_precedence(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str0, $str1 FROM %s'  % (bucket.name) +\
            ' ORDER BY $str0, $str1'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

            query_template = 'SELECT $str0, $str1 FROM %s'  % (bucket.name) +\
            ' ORDER BY $str1, $str0'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_order_by_satisfy(self):
        for bucket in self.buckets:
            query_template = 'SELECT $str0, $list_obj0 FROM %s AS employee ' % (bucket.name) +\
                        'WHERE ANY vm IN employee.$list_obj0 SATISFIES vm.$_list_obj0_int0 > 5 AND' +\
                        ' vm.$_list_obj0_str0 = "ubuntu" END ORDER BY $str0, $list_obj0[0].$_list_obj0_int0'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

##############################################################################################
#
#   DISTINCT
##############################################################################################

    def test_distinct(self):
        for bucket in self.buckets:
            query_template = 'SELECT DISTINCT $str1 FROM %s ORDER BY $str1'  % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_distinct_nested(self):
        for bucket in self.buckets:
            query_template = 'SELECT DISTINCT $obj0.$_obj0_int0 as VAR FROM %s '  % (bucket.name) +\
                         'ORDER BY $obj0.$_obj0_int0'
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

            query_template = 'SELECT DISTINCT $list_str0[0] as skill' +\
                         ' FROM %s ORDER BY $list_str0[0]'  % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

            self.query = 'SELECT DISTINCT $obj0.* FROM %s'  % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

##############################################################################################
#
#   COMPLEX PATHS
##############################################################################################

    def test_simple_complex_paths(self):
        for bucket in self.buckets:
            query_template = 'SELECT $_obj0_int0 FROM %s.$obj0'  % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_alias_complex_paths(self):
        for bucket in self.buckets:
            query_template = 'SELECT $_obj0_int0 as new_attribute FROM %s.$obj0'  % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

    def test_where_complex_paths(self):
        for bucket in self.buckets:
            query_template = 'SELECT $_obj0_int0 FROM %s.$obj0 WHERE $_obj0_int0 = 1'  % (bucket.name)
            actual_result, expected_result = self.run_query_from_template(query_template)
            self._verify_results(actual_result['results'], expected_result)

##############################################################################################
#
#   COMMON FUNCTIONS
##############################################################################################

    def run_query_from_template(self, query_template):
        self.query = self.gen_results.generate_query(query_template)
        expected_result = self.gen_results.generate_expected_result()
        actual_result = self.run_cbq_query()
        return actual_result, expected_result

    def negative_common_body(self, queries_errors={}):
        if not queries_errors:
            self.fail("No queries to run!")
        for bucket in self.buckets:
            for query_template, error in queries_errors.iteritems():
                try:
                    query = self.gen_results.generate_query(query_template)
                    actual_result = self.run_cbq_query(query.format(bucket.name))
                except CBQError as ex:
                    self.log.error(ex)
                    self.assertTrue(str(ex).find(error) != -1,
                                    "Error is incorrect.Actual %s.\n Expected: %s.\n" %(
                                                                str(ex).split(':')[-1], error))
                else:
                    self.fail("There was no errors. Error expected: %s" % error)

    def run_cbq_query(self, query=None, min_output_size=10, server=None):
        if query is None:
            query = self.query
        if server is None:
           server = self.master
           if server.ip == "127.0.0.1":
            self.n1ql_port = server.n1ql_port
        else:
            if server.ip == "127.0.0.1":
                self.n1ql_port = server.n1ql_port
            if self.input.tuq_client and "client" in self.input.tuq_client:
                server = self.tuq_client
        if self.n1ql_port == None or self.n1ql_port == '':
            self.n1ql_port = self.input.param("n1ql_port", 8093)
            if not self.n1ql_port:
                self.log.info(" n1ql_port is not defined, processing will not proceed further")
                raise Exception("n1ql_port is not defined, processing will not proceed further")
        if self.use_rest:
            result = RestConnection(server).query_tool(query, self.n1ql_port)
        else:
            if self.version == "git_repo":
                output = self.shell.execute_commands_inside("$GOPATH/src/github.com/couchbaselabs/tuqtng/" +\
                                                            "tuq_client/tuq_client " +\
                                                            "-engine=http://%s:8093/" % server.ip,
                                                       subcommands=[query,],
                                                       min_output_size=20,
                                                       end_msg='tuq_client>')
            else:
                output = self.shell.execute_commands_inside("/tmp/tuq/cbq -engine=http://%s:8093/" % server.ip,
                                                           subcommands=[query,],
                                                           min_output_size=20,
                                                           end_msg='cbq>')
            result = self._parse_query_output(output)
        if isinstance(result, str) or 'errors' in result:
            raise CBQError(result, server.ip)
        self.log.info("TOTAL ELAPSED TIME: %s" % result["metrics"]["elapsedTime"])
        return result

    def build_url(self, version):
        info = self.shell.extract_remote_info()
        type = info.distribution_type.lower()
        if type in ["ubuntu", "centos", "red hat"]:
            url = "https://s3.amazonaws.com/packages.couchbase.com/releases/couchbase-query/dp1/"
            url += "couchbase-query_%s_%s_linux.tar.gz" %(
                                version, info.architecture_type)
        #TODO for windows
        return url

    def _build_tuq(self, server):
        if self.version == "git_repo":
            os = self.shell.extract_remote_info().type.lower()
            if os != 'windows':
                goroot = testconstants.LINUX_GOROOT
                gopath = testconstants.LINUX_GOPATH
            else:
                goroot = testconstants.WINDOWS_GOROOT
                gopath = testconstants.WINDOWS_GOPATH
            if self.input.tuq_client and "gopath" in self.input.tuq_client:
                gopath = self.input.tuq_client["gopath"]
            if self.input.tuq_client and "goroot" in self.input.tuq_client:
                goroot = self.input.tuq_client["goroot"]
            cmd = "rm -rf {0}/src/github.com".format(gopath)
            self.shell.execute_command(cmd)
            cmd= 'export GOROOT={0} && export GOPATH={1} &&'.format(goroot, gopath) +\
                ' export PATH=$PATH:$GOROOT/bin && ' +\
                'go get github.com/couchbaselabs/tuqtng;' +\
                'cd $GOPATH/src/github.com/couchbaselabs/tuqtng; ' +\
                'go get -d -v ./...; cd .'
            self.shell.execute_command(cmd)
            cmd = 'export GOROOT={0} && export GOPATH={1} &&'.format(goroot, gopath) +\
                ' export PATH=$PATH:$GOROOT/bin && ' +\
                'cd $GOPATH/src/github.com/couchbaselabs/tuqtng; go build; cd .'
            self.shell.execute_command(cmd)
            cmd = 'export GOROOT={0} && export GOPATH={1} &&'.format(goroot, gopath) +\
                ' export PATH=$PATH:$GOROOT/bin && ' +\
                'cd $GOPATH/src/github.com/couchbaselabs/tuqtng/tuq_client; go build; cd .'
            self.shell.execute_command(cmd)
        else:
            cbq_url = self.build_url(self.version)
            #TODO for windows
            cmd = "cd /tmp; mkdir tuq;cd tuq; wget {0} -O tuq.tar.gz;".format(cbq_url)
            cmd += "tar -xvf tuq.tar.gz;rm -rf tuq.tar.gz"
            self.shell.execute_command(cmd)

    def _start_command_line_query(self, server):
        self.shell.execute_command("export NS_SERVER_CBAUTH_URL=\"http://{0}:{1}/_cbauth\"".format(server.ip,server.port))
        self.shell.execute_command("export NS_SERVER_CBAUTH_USER=\"{0}\"".format(server.rest_username))
        self.shell.execute_command("export NS_SERVER_CBAUTH_PWD=\"{0}\"".format(server.rest_password))
        self.shell.execute_command("export NS_SERVER_CBAUTH_RPC_URL=\"http://{0}:{1}/cbauth-demo\"".format(server.ip,server.port))
        if self.version == "git_repo":
            os = self.shell.extract_remote_info().type.lower()
            if os != 'windows':
                gopath = testconstants.LINUX_GOPATH
            else:
                gopath = testconstants.WINDOWS_GOPATH
            if self.input.tuq_client and "gopath" in self.input.tuq_client:
                gopath = self.input.tuq_client["gopath"]
            if os == 'windows':
                cmd = "cd %s/src/github.com/couchbaselabs/query/server/main; " % (gopath) +\
                "./cbq-engine.exe -datastore http://%s:%s/ >/dev/null 2>&1 &" %(
                                                                server.ip, server.port)
            else:
                cmd = "cd %s/src/github.com/couchbaselabs/query//server/main; " % (gopath) +\
                "./cbq-engine -datastore http://%s:%s/ >n1ql.log 2>&1 &" %(
                                                                server.ip, server.port)
            self.shell.execute_command(cmd)
        elif self.version == "sherlock":
            os = self.shell.extract_remote_info().type.lower()
            if os != 'windows':
                couchbase_path = testconstants.LINUX_COUCHBASE_BIN_PATH
            else:
                couchbase_path = testconstants.WIN_COUCHBASE_BIN_PATH
            if self.input.tuq_client and "sherlock_path" in self.input.tuq_client:
                couchbase_path = "%s/bin" % self.input.tuq_client["sherlock_path"]
                print "PATH TO SHERLOCK: %s" % couchbase_path
            if os == 'windows':
                cmd = "cd %s; " % (couchbase_path) +\
                "./cbq-engine.exe -datastore http://%s:%s/ >/dev/null 2>&1 &" %(
                                                                server.ip, server.port)
            else:
                cmd = "cd %s; " % (couchbase_path) +\
                "./cbq-engine -datastore http://%s:%s/ >n1ql.log 2>&1 &" %(
                                                                server.ip, server.port)
                n1ql_port = self.input.param("n1ql_port", None)
                if server.ip == "127.0.0.1" and server.n1ql_port:
                    n1ql_port = server.n1ql_port
                if n1ql_port:
                    cmd = "cd %s; " % (couchbase_path) +\
                './cbq-engine -datastore http://%s:%s/ -http=":%s">n1ql.log 2>&1 &' %(
                                                                server.ip, server.port, n1ql_port)
            self.shell.execute_command(cmd)
        else:
            os = self.shell.extract_remote_info().type.lower()
            if os != 'windows':
                cmd = "cd /tmp/tuq;./cbq-engine -couchbase http://%s:%s/ >/dev/null 2>&1 &" %(
                                                                server.ip, server.port)
            else:
                cmd = "cd /cygdrive/c/tuq;./cbq-engine.exe -couchbase http://%s:%s/ >/dev/null 2>&1 &" %(
                                                                server.ip, server.port)
            self.shell.execute_command(cmd)

    def _parse_query_output(self, output):
        if output.find("cbq>") == 0:
            output = output[output.find("cbq>") + 4:].strip()
        if output.find("tuq_client>") == 0:
            output = output[output.find("tuq_client>") + 11:].strip()
        if output.find("cbq>") != -1:
            output = output[:output.find("cbq>")].strip()
        if output.find("tuq_client>") != -1:
            output = output[:output.find("tuq_client>")].strip()
        return json.loads(output)

    def generate_docs(self, num_items, start=0):
        try:
            return getattr(self, 'generate_docs_' + self.dataset)(num_items, start)
        except:
            self.fail("There is no dataset %s, please enter a valid one" % self.dataset)

    def generate_docs_default(self, docs_per_day, start=0):
        json_generator = JsonGenerator()
        return json_generator.generate_docs_employee(docs_per_day, start)

    def generate_docs_sabre(self, docs_per_day, start=0):
        json_generator = JsonGenerator()
        return json_generator.generate_docs_sabre(docs_per_day, start)

    def generate_docs_employee(self, docs_per_day, start=0):
        json_generator = JsonGenerator()
        return json_generator.generate_docs_employee_data(docs_per_day = docs_per_day, start = start)

    def generate_docs_simple(self, docs_per_day, start=0):
        json_generator = JsonGenerator()
        return json_generator.generate_docs_employee_simple_data(docs_per_day = docs_per_day, start = start)

    def generate_docs_sales(self, docs_per_day, start=0):
        json_generator = JsonGenerator()
        return json_generator.generate_docs_employee_sales_data(docs_per_day = docs_per_day, start = start)

    def generate_docs_bigdata(self, docs_per_day, start=0):
        json_generator = JsonGenerator()
        return json_generator.generate_docs_bigdata(docs_per_day = docs_per_day * 1000,
            start = start, value_size = self.value_size)


    def _verify_results(self, actual_result, expected_result, missing_count = 1, extra_count = 1):
        if len(actual_result) != len(expected_result):
            missing, extra = self.check_missing_and_extra(actual_result, expected_result)
            self.log.error("Missing items: %s.\n Extra items: %s" % (missing[:missing_count], extra[:extra_count]))
            self.fail("Results are incorrect.Actual num %s. Expected num: %s.\n" % (
                                            len(actual_result), len(expected_result)))
        if self.max_verify is not None:
            actual_result = actual_result[:self.max_verify]
            expected_result = expected_result[:self.max_verify]

        msg = "Results are incorrect.\n Actual first and last 100:  %s.\n ... \n %s" +\
        "Expected first and last 100: %s.\n  ... \n %s"
        self.assertTrue(actual_result == expected_result,
                          msg % (actual_result[:100],actual_result[-100:],
                                 expected_result[:100],expected_result[-100:]))

    def check_missing_and_extra(self, actual, expected):
        missing = []
        extra = []
        for item in actual:
            if not (item in expected):
                 extra.append(item)
        for item in expected:
            if not (item in actual):
                missing.append(item)
        return missing, extra

    def sort_nested_list(self, result):
        actual_result = []
        for item in result:
            curr_item = {}
            for key, value in item.iteritems():
                if isinstance(value, list) or isinstance(value, set):
                    curr_item[key] = sorted(value)
                else:
                    curr_item[key] = value
            actual_result.append(curr_item)
        return actual_result

    def configure_gomaxprocs(self):
        max_proc = self.input.param("gomaxprocs", None)
        cmd = "export GOMAXPROCS=%s" % max_proc
        for server in self.servers:
            shell_connection = RemoteMachineShellConnection(self.master)
            shell_connection.execute_command(cmd)

    def create_primary_index_for_3_0_and_greater(self):
        self.log.info("CHECK FOR PRIMARY INDEXES")
        rest = RestConnection(self.master)
        versions = rest.get_nodes_versions()
        ddoc_name = 'ddl_#primary'
        if versions[0].startswith("3"):
            try:
                rest.get_ddoc(self.buckets[0], ddoc_name)
            except ReadDocumentException:
                for bucket in self.buckets:
                    self.log.info("Creating primary index for %s ..." % bucket.name)
                    self.query = "CREATE PRIMARY INDEX ON %s " % (bucket.name)
                    try:
                        self.run_cbq_query()
                    except Exception, ex:
                        self.log.error('ERROR during index creation %s' % str(ex))
