# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ducktape.mark import parametrize
from ducktape.tests.test import Test
from ducktape.utils.util import wait_until

from kafkatest.services.kafka import KafkaService
from kafkatest.services.streams import StreamsBrokerCompatibilityService
from kafkatest.services.verifiable_consumer import VerifiableConsumer
from kafkatest.services.zookeeper import ZookeeperService
from kafkatest.version import DEV_BRANCH, LATEST_0_11_0, LATEST_0_10_2, LATEST_0_10_1, LATEST_0_10_0, LATEST_0_9, LATEST_0_8_2, KafkaVersion


class StreamsBrokerCompatibility(Test):
    """
    These tests validates that
    - Streams 0.11+ w/ EOS fails fast for older brokers 0.10.2 and 0.10.1
    - Streams 0.11+ w/o EOS works for older brokers 0.10.2 and 0.10.1
    - Streams fails fast for 0.10.0 brokers
    - Streams times-out for pre-0.10.0 brokers
    """

    input = "brokerCompatibilitySourceTopic"
    output = "brokerCompatibilitySinkTopic"

    def __init__(self, test_context):
        super(StreamsBrokerCompatibility, self).__init__(test_context=test_context)
        self.zk = ZookeeperService(test_context, num_nodes=1)
        self.kafka = KafkaService(test_context,
                                  num_nodes=1,
                                  zk=self.zk,
                                  topics={
                                      self.input: {'partitions': 1, 'replication-factor': 1},
                                      self.output: {'partitions': 1, 'replication-factor': 1}
                                  })
        self.consumer = VerifiableConsumer(test_context,
                                           1,
                                           self.kafka,
                                           self.output,
                                           "stream-broker-compatibility-verify-consumer")

    def setUp(self):
        self.zk.start()

   
    @parametrize(broker_version=str(LATEST_0_10_2))
    @parametrize(broker_version=str(LATEST_0_10_1))
    def test_fail_fast_on_incompatible_brokers_if_eos_enabled(self, broker_version):
        self.kafka.set_version(KafkaVersion(broker_version))
        self.kafka.start()

        processor = StreamsBrokerCompatibilityService(self.test_context, self.kafka, True)
        processor.start()

        processor.node.account.ssh(processor.start_cmd(processor.node))
        with processor.node.account.monitor_log(processor.STDERR_FILE) as monitor:
            monitor.wait_until('Exception in thread "main" org.apache.kafka.streams.errors.StreamsException: Setting processing.guarantee=exactly_once requires broker version 0.11.0.x or higher.',
                               timeout_sec=60,
                               err_msg="Never saw 'EOS requires broker version 0.11+' error message " + str(processor.node.account))

        self.kafka.stop()

    @parametrize(broker_version=str(LATEST_0_11_0))
    @parametrize(broker_version=str(LATEST_0_10_2))
    @parametrize(broker_version=str(LATEST_0_10_1))
    def test_compatible_brokers_eos_disabled(self, broker_version):
        self.kafka.set_version(KafkaVersion(broker_version))
        self.kafka.start()

        processor = StreamsBrokerCompatibilityService(self.test_context, self.kafka, False)
        processor.start()

        self.consumer.start()

        processor.wait()

        wait_until(lambda: self.consumer.total_consumed() > 0, timeout_sec=30, err_msg="Did expect to read a message but got none within 30 seconds.")

        self.consumer.stop()
        self.kafka.stop()

    @parametrize(broker_version=str(LATEST_0_10_0))
    def test_fail_fast_on_incompatible_brokers(self, broker_version):
        self.kafka.set_version(KafkaVersion(broker_version))
        self.kafka.start()

        processor = StreamsBrokerCompatibilityService(self.test_context, self.kafka, False)
        processor.start()

        processor.node.account.ssh(processor.start_cmd(processor.node))
        with processor.node.account.monitor_log(processor.STDERR_FILE) as monitor:
            monitor.wait_until('Exception in thread "main" org.apache.kafka.streams.errors.StreamsException: Kafka Streams requires broker version 0.10.1.x or higher.',
                        timeout_sec=60,
                        err_msg="Never saw 'Streams requires broker verion 0.10.1+' error message " + str(processor.node.account))

        self.kafka.stop()

    @parametrize(broker_version=str(LATEST_0_9))
    @parametrize(broker_version=str(LATEST_0_8_2))
    def test_timeout_on_pre_010_brokers(self, broker_version):
        self.kafka.set_version(KafkaVersion(broker_version))
        self.kafka.start()

        processor = StreamsBrokerCompatibilityService(self.test_context, self.kafka, False)
        processor.start()

        processor.node.account.ssh(processor.start_cmd(processor.node))
        with processor.node.account.monitor_log(processor.STDERR_FILE) as monitor:
            monitor.wait_until('Exception in thread "main" org.apache.kafka.streams.errors.BrokerNotFoundException: Could not find any available broker.',
                               timeout_sec=60,
                               err_msg="Never saw 'no available brokers' error message " + str(processor.node.account))

        self.kafka.stop()
