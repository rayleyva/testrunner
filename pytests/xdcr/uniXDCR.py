from threading import Thread
import copy

from couchbase_helper.documentgenerator import BlobGenerator
from remote.remote_util import RemoteMachineShellConnection
from membase.api.rest_client import RestConnection
from memcached.helper.data_helper import LoadWithMcsoda
from xdcrnewbasetests import XDCRNewBaseTest
from xdcrnewbasetests import NodeHelper
from xdcrnewbasetests import Utility, BUCKET_NAME, OPS


# Assumption that at least 2 nodes on every cluster
class unidirectional(XDCRNewBaseTest):
    def setUp(self):
        super(unidirectional, self).setUp()
        self.src_cluster = self.get_cb_cluster_by_name('C1')
        self.src_master = self.src_cluster.get_master_node()
        self.dest_cluster = self.get_cb_cluster_by_name('C2')
        self.dest_master = self.dest_cluster.get_master_node()

    def tearDown(self):
        super(unidirectional, self).tearDown()

    """Testing Unidirectional load( Loading only at source) Verifying whether XDCR replication is successful on
    subsequent destination clusters.Create/Update/Delete operations are performed based on doc-ops specified by the user. """

    def load_with_ops(self):
        self.setup_xdcr_and_load()
        self.perform_update_delete()
        self.verify_results()

    """Testing Unidirectional load( Loading only at source) Verifying whether XDCR replication is successful on
    subsequent destination clusters. Create/Update/Delete are performed in parallel- doc-ops specified by the user. """

    def load_with_async_ops(self):
        self.setup_xdcr_and_load()
        self.async_perform_update_delete()
        self.verify_results()

    def load_with_async_ops_diff_data_size(self):
        # Load 1 item with size 1
        # 52 alphabets (small and capital letter)
        self.src_cluster.load_all_buckets(52, value_size=1)
        # Load items with below sizes of 1M
        self.src_cluster.load_all_buckets(5, value_size=1000000)
        # Load items with size 10MB
        # Getting memory issue with 20MB data on VMs.
        self.src_cluster.load_all_buckets(1, value_size=10000000)

        self.verify_results()

    """Testing Unidirectional load( Loading only at source). Failover node at Source/Destination while
    Create/Update/Delete are performed after based on doc-ops specified by the user.
    Verifying whether XDCR replication is successful on subsequent destination clusters. """

    def load_with_ops_with_warmup(self):
        self.setup_xdcr_and_load()
        warmupnodes = []
        if "C1" in self._warmup:
            warmupnodes.append(self.src_cluster.warmup_node())
        if "C2" in self._warmup:
            warmupnodes.append(self.dest_cluster.warmup_node())

        self.sleep(self._wait_timeout)
        self.perform_update_delete()
        self.sleep(self._wait_timeout / 2)

        NodeHelper.wait_warmup_completed(warmupnodes)

        self.verify_results()

    def load_with_ops_with_warmup_master(self):
        self.setup_xdcr_and_load()
        warmupnodes = []
        if "C1" in self._warmup:
            warmupnodes.append(self.src_cluster.warmup_node(master=True))
        if "C2" in self._warmup:
            warmupnodes.append(self.dest_cluster.warmup_node(master=True))

        self.sleep(self._wait_timeout)
        self.perform_update_delete()
        self.sleep(self._wait_timeout / 2)

        NodeHelper.wait_warmup_completed(warmupnodes)

        self.verify_results()

    def load_with_async_ops_with_warmup(self):
        self.setup_xdcr_and_load()
        warmupnodes = []
        if "C1" in self._warmup:
            warmupnodes.append(self.src_cluster.warmup_node())
        if "C2" in self._warmup:
            warmupnodes.append(self.dest_cluster.warmup_node())

        self.sleep(self._wait_timeout)
        self.async_perform_update_delete()
        self.sleep(self._wait_timeout / 2)

        NodeHelper.wait_warmup_completed(warmupnodes)

        self.verify_results()

    def load_with_async_ops_with_warmup_master(self):
        self.setup_xdcr_and_load()
        warmupnodes = []
        if "C1" in self._warmup:
            warmupnodes.append(self.src_cluster.warmup_node(master=True))
        if "C2" in self._warmup:
            warmupnodes.append(self.dest_cluster.warmup_node(master=True))

        self.sleep(self._wait_timeout)
        self.async_perform_update_delete()
        self.sleep(self._wait_timeout / 2)

        NodeHelper.wait_warmup_completed(warmupnodes)

        self.verify_results()

    def load_with_failover(self):
        self.setup_xdcr_and_load()

        if "C1" in self._failover:
            self.src_cluster.failover_and_rebalance_nodes()
        if "C2" in self._failover:
            self.dest_cluster.failover_and_rebalance_nodes()

        self.sleep(self._wait_timeout / 6)
        self.perform_update_delete()

        self.verify_results()

    def load_with_failover_then_add_back(self):

        self.setup_xdcr_and_load()

        if "C1" in self._failover:
            self.src_cluster.failover_and_rebalance_nodes(rebalance=False)
            self.src_cluster.add_back_node()
        if "C2" in self._failover:
            self.dest_cluster.failover_and_rebalance_nodes(rebalance=False)
            self.dest_cluster.add_back_node()

        self.perform_update_delete()

        self.verify_results()

    """Testing Unidirectional load( Loading only at source). Failover node at Source/Destination while
    Create/Update/Delete are performed in parallel based on doc-ops specified by the user.
    Verifying whether XDCR replication is successful on subsequent destination clusters. """

    def load_with_failover_master(self):
        self.setup_xdcr_and_load()

        if "C1" in self._failover:
            self.src_cluster.failover_and_rebalance_master()
        if "C2" in self._failover:
            self.dest_cluster.failover_and_rebalance_master()

        self.sleep(self._wait_timeout / 6)
        self.perform_update_delete()

        self.verify_results()

    """Testing Unidirectional load( Loading only at source). Failover node at Source/Destination while
    Create/Update/Delete are performed in parallel based on doc-ops specified by the user.
    Verifying whether XDCR replication is successful on subsequent destination clusters. """

    def load_with_async_failover(self):
        self.setup_xdcr_and_load()

        tasks = []
        if "C1" in self._failover:
            tasks.append(self.src_cluster.async_failover())
        if "C2" in self._failover:
            tasks.append(self.dest_cluster.async_failover())

        self.perform_update_delete()
        self.sleep(self._wait_timeout / 4)

        for task in tasks:
            task.result()

        if "C1" in self._failover:
            self.src_cluster.rebalance_failover_nodes()
        if "C2" in self._failover:
            self.dest_cluster.rebalance_failover_nodes()

        self.verify_results()

    """Replication with compaction ddocs and view queries on both clusters.

        This test begins by loading a given number of items on the source cluster.
        It creates num_views as development/production view with default
        map view funcs(_is_dev_ddoc = True by default) on both clusters.
        Then we disabled compaction for ddoc on src cluster. While we don't reach
        expected fragmentation for ddoc on src cluster we update docs and perform
        view queries for all views. Then we start compaction when fragmentation
        was reached fragmentation_value. When compaction was completed we perform
        a full verification: wait for the disk queues to drain
        and then verify that there has been any data loss on all clusters."""
    def replication_with_ddoc_compaction(self):
        self.setup_xdcr_and_load()

        num_views = self._input.param("num_views", 5)
        is_dev_ddoc = self._input.param("is_dev_ddoc", True)
        fragmentation_value = self._input.param("fragmentation_value", 80)
        for bucket in self.src_cluster.get_buckets():
            views = Utility.make_default_views(bucket.name, num_views, is_dev_ddoc)

        ddoc_name = "ddoc1"
        prefix = ("", "dev_")[is_dev_ddoc]

        query = {"full_set": "true", "stale": "false"}

        tasks = self.src_cluster.async_create_views(ddoc_name, views, BUCKET_NAME.DEFAULT)
        tasks += self.dest_cluster.async_create_views(ddoc_name, views, BUCKET_NAME.DEFAULT)
        for task in tasks:
            task.result(self._poll_timeout)

        self.src_cluster.disable_compaction()
        fragmentation_monitor = self.src_cluster.async_monitor_view_fragmentation(prefix + ddoc_name, fragmentation_value, BUCKET_NAME.DEFAULT)

        # generate load until fragmentation reached
        while fragmentation_monitor.state != "FINISHED":
            # update docs to create fragmentation
            self.src_cluster.update_delete_data(OPS.UPDATE)
            for view in views:
                # run queries to create indexes
                self.src_cluster.query_view(prefix + ddoc_name, view.name, query)
        fragmentation_monitor.result()

        compaction_task = self.src_cluster.async_compact_view(prefix + ddoc_name, 'default')

        self.assertTrue(compaction_task.result())

        self.verify_results()

    """Replication with disabled/enabled ddoc compaction on source cluster.

        This test begins by loading a given number of items on the source cluster.
        Then we disabled or enabled compaction on both clusters( set via params).
        Then we mutate and delete data on the source cluster 3 times.
        After deletion we recreate deleted items. When data was changed 3 times
        we perform a full verification: wait for the disk queues to drain
        and then verify that there has been no data loss on both all clusters."""
    def replication_with_disabled_ddoc_compaction(self):
        self.setup_xdcr_and_load()

        if "C1" in self._disable_compaction:
            self.src_cluster.disable_compaction()
        if "C2" in self._disable_compaction:
            self.dest_cluster.disable_compaction()

        # perform doc's ops 3 times to increase rev number
        for _ in range(3):
            self.async_perform_update_delete()
            # restore(re-creating) deleted items
            if 'C1' in self._del_clusters:
                c1_kv_gen = self.src_cluster.get_kv_gen()
                gen_delete = copy.deepcopy(c1_kv_gen[OPS.DELETE])
                self.src_cluster.load_all_buckets_from_generator(kv_gen=gen_delete)
                self.sleep(5)

        self.verify_results()

    def replication_while_rebooting_a_non_master_destination_node(self):
        self.setup_xdcr_and_load()
        self.src_cluster.set_xdcr_param("xdcrFailureRestartInterval", 1)
        self.perform_update_delete()
        self.sleep(self._wait_timeout / 2)
        rebooted_node = self.dest_cluster.reboot_one_node(self)
        NodeHelper.wait_node_restarted(rebooted_node, self, wait_time=self._wait_timeout * 4, wait_if_warmup=True)

        self.verify_results()

    def replication_with_firewall_enabled(self):
        self.src_cluster.set_xdcr_param("xdcrFailureRestartInterval", 1)
        self.setup_xdcr_and_load()
        self.perform_update_delete()

        NodeHelper.enable_firewall(self.dest_master)
        self.sleep(30)
        NodeHelper.disable_firewall(self.dest_master)
        self.verify_results()

    """Testing Unidirectional append ( Loading only at source) Verifying whether XDCR replication is successful on
    subsequent destination clusters. """

    def test_append(self):
        self.setup_xdcr_and_load()
        self.verify_results()
        loop_count = self._input.param("loop_count", 20)
        for i in xrange(loop_count):
            self.log.info("Append iteration # %s" % i)
            gen_append = BlobGenerator('loadOne', 'loadOne', self._value_size, end=self._num_items)
            self.src_cluster.load_all_buckets_from_generator(gen_append, ops=OPS.APPEND, batch_size=1)
            self.sleep(self._wait_timeout)
        self.verify_results()

    '''
    This method runs cbcollectinfo tool after setting up uniXDCR and check
    whether the log generated by cbcollectinfo contains xdcr log file or not.
    '''
    def collectinfotest_for_xdcr(self):
        self.load_with_ops()
        self.node_down = self._input.param("node_down", False)
        self.log_filename = self._input.param("file_name", "collectInfo")
        self.shell = RemoteMachineShellConnection(self.src_master)
        self.shell.execute_cbcollect_info("%s.zip" % (self.log_filename))
        from clitest import collectinfotest
        # HACK added self.buckets data member.
        self.buckets = self.src_cluster.get_buckets()
        collectinfotest.CollectinfoTests.verify_results(
            self, self.log_filename
        )

    """ Verify the fix for MB-9548"""
    def test_verify_replications_stream_delete(self):
        self.setup_xdcr_and_load()
        self.verify_results()
        rest_conn = RestConnection(self.src_master)
        replications = rest_conn.get_replications()
        self.assertTrue(replications, "Number of replication streams should not be 0")
        self.src_cluster.delete_all_buckets()

        replications = rest_conn.get_replications()
        self.assertTrue(not replications, "No replication streams should exists after deleting the buckets")

    """ Verify fix for MB-9862"""
    def test_verify_memcache_connections(self):
        allowed_memcached_conn = self._input.param("allowed_connections", 100)
        max_ops_per_second = self._input.param("max_ops_per_second", 2500)
        min_item_size = self._input.param("min_item_size", 128)
        num_docs = self._input.param("num_docs", 30000)
        # start load, max_ops_per_second is the combined limit for all buckets
        mcsodaLoad = LoadWithMcsoda(self.src_master, num_docs, prefix='')
        mcsodaLoad.cfg["max-ops"] = 0
        mcsodaLoad.cfg["max-ops-per-sec"] = max_ops_per_second
        mcsodaLoad.cfg["exit-after-creates"] = 1
        mcsodaLoad.cfg["min-value-size"] = min_item_size
        mcsodaLoad.cfg["json"] = 0
        mcsodaLoad.cfg["batch"] = 100
        loadDataThread = Thread(target=mcsodaLoad.load_data,
                                  name='mcloader_default')
        loadDataThread.daemon = True
        loadDataThread.start()

        src_remote_shell = RemoteMachineShellConnection(self.src_master)
        machine_type = src_remote_shell.extract_remote_info().type.lower()
        while (loadDataThread.isAlive() and machine_type == 'linux'):
            command = "netstat -lpnta | grep 11210 | grep TIME_WAIT | wc -l"
            output, _ = src_remote_shell.execute_command(command)
            if int(output[0]) > allowed_memcached_conn:
                # stop load
                mcsodaLoad.load_stop()
                loadDataThread.join()
                self.fail("Memcached connections {0} are increased above {1} \
                            on Source node".format(
                                                   allowed_memcached_conn,
                                                   int(output[0])))
            self.sleep(5)

        # stop load
        mcsodaLoad.load_stop()
        loadDataThread.join()

    # Test to verify MB-10116
    def verify_ssl_private_key_not_present_in_logs(self):
        zip_file = "%s.zip" % (self._input.param("file_name", "collectInfo"))
        try:
            self.shell = RemoteMachineShellConnection(self.src_master)
            self.load_with_ops()
            self.shell.execute_cbcollect_info(zip_file)
            if self.shell.extract_remote_info().type.lower() != "windows":
                command = "unzip %s" % (zip_file)
                output, error = self.shell.execute_command(command)
                self.shell.log_command_output(output, error)
                if len(error) > 0:
                    raise Exception("unable to unzip the files. Check unzip command output for help")
                cmd = 'grep -R "BEGIN RSA PRIVATE KEY" cbcollect_info*/'
                output, _ = self.shell.execute_command(cmd)
            else:
                cmd = "curl -0 http://{1}:{2}@{0}:8091/diag 2>/dev/null | grep 'BEGIN RSA PRIVATE KEY'".format(
                                                    self.src_master.ip,
                                                    self.src_master.rest_username,
                                                    self.src_master.rest_password)
                output, _ = self.shell.execute_command(cmd)
            self.assertTrue(not output, "XDCR SSL Private Key is found diag logs -> %s" % output)
        finally:
            self.shell.delete_files(zip_file)
            self.shell.delete_files("cbcollect_info*")

    # Buckets States
    def delete_recreate_dest_buckets(self):
        self.setup_xdcr_and_load()

        # Remove destination buckets
        self.dest_cluster.delete_all_buckets()

        # Code for re-create_buckets
        self.create_buckets_on_cluster("C2")

        self._resetup_replication_for_recreate_buckets("C2")

        self.async_perform_update_delete()
        self.verify_results()

    def flush_dest_buckets(self):
        self.setup_xdcr_and_load()

        # flush destination buckets
        self.dest_cluster.flush_buckets()

        self.async_perform_update_delete()
        self.verify_results()

    # Nodes Crashing Scenarios
    def __kill_processes(self, crashed_nodes=[]):
        for node in crashed_nodes:
            NodeHelper.kill_erlang(node)

    def __start_cb_server(self, node):
        shell = RemoteMachineShellConnection(node)
        shell.start_couchbase()
        shell.disconnect()

    def test_node_crash_master(self):
        self.setup_xdcr_and_load()

        crashed_nodes = []
        crash = self._input.param("crash", "").split('-')
        if "C1" in crash:
            crashed_nodes.append(self.src_master)
        if "C2" in crash:
            crashed_nodes.append(self.dest_master)

        self.__kill_processes(crashed_nodes)

        for crashed_node in crashed_nodes:
            self.__start_cb_server(crashed_node)
        NodeHelper.wait_warmup_completed(crashed_nodes)

        self.async_perform_update_delete()
        self.verify_results()

    # Disaster at site.
    # 1. Crash Source Cluster., Sleep n second
    # 2. Crash Dest Cluster.
    # 3. Wait for Source Cluster to warmup. Load more data and perform mutations on Src.
    # 4. Wait for Dest to warmup.
    # 5. Verify data.
    def test_node_crash_cluster(self):
        self.setup_xdcr_and_load()

        crashed_nodes = []
        crash = self._input.param("crash", "").split('-')
        if "C1" in crash:
            crashed_nodes += self.src_cluster.get_nodes()
            self.__kill_processes(crashed_nodes)
            self.sleep(30)
        if "C2" in crash:
            crashed_nodes += self.dest_cluster.get_nodes()
            self.__kill_processes(crashed_nodes)

        for crashed_node in crashed_nodes:
            self.__start_cb_server(crashed_node)

        if "C1" in crash:
            NodeHelper.wait_warmup_completed(self.src_cluster.get_nodes())
            gen_create = BlobGenerator('loadTwo', 'loadTwo', self._value_size, end=self._num_items)
            self.src_cluster.load_all_buckets_from_generator(kv_gen=gen_create)

        self.async_perform_update_delete()

        if "C2" in crash:
            NodeHelper.wait_warmup_completed(self.dest_cluster.get_nodes())

        self.verify_results()

    """ Test if replication restarts 60s after idle xdcr following dest bucket flush """
    def test_idle_xdcr_dest_flush(self):
        self.setup_xdcr_and_load()
        self.verify_results()

        bucket = self.dest_cluster.get_bucket_by_name(BUCKET_NAME.DEFAULT)
        self.dest_cluster.flush_buckets([bucket])

        self.sleep(self._wait_timeout)

        self.verify_results()

    """ Test if replication restarts 60s after idle xdcr following dest bucket recreate """
    def test_idle_xdcr_dest_recreate(self):
        self.setup_xdcr_and_load()
        self.verify_results()

        bucket = self.dest_cluster.get_bucket_by_name(BUCKET_NAME.DEFAULT)
        self.dest_cluster.delete_bucket(BUCKET_NAME.DEFAULT)

        self.dest_cluster.create_default_bucket(bucket.bucket_size)

        self.sleep(self._wait_timeout)

        self.verify_results()

    """ Test if replication restarts 60s after idle xdcr following dest failover """
    def test_idle_xdcr_dest_failover(self):
        self.setup_xdcr_and_load()
        self.verify_results()

        self.dest_cluster.failover_and_rebalance_nodes()

        self.sleep(self._wait_timeout)

        self.verify_results()
