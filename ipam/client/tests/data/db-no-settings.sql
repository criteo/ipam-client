BEGIN TRANSACTION;
CREATE TABLE "settings" (
  "id" INTEGER PRIMARY KEY,
  "version" varchar(5) DEFAULT NULL
);
CREATE TABLE "ipaddresses" (
  "id" INTEGER PRIMARY KEY,
  "subnetId" int(11)  DEFAULT NULL,
  "ip_addr" varchar(100) NOT NULL,
  "description" varchar(64) DEFAULT NULL,
  "dns_name" varchar(64) NOT NULL,
  "mac" varchar(20) DEFAULT NULL,
  "owner" varchar(32) DEFAULT NULL,
  "state" varchar(1) DEFAULT '1',
  "switch" int(11)  DEFAULT NULL,
  "port" varchar(32) DEFAULT NULL,
  "note" text,
  "lastSeen" datetime DEFAULT '0000-00-00 00:00:00',
  "excludePing" binary(1) DEFAULT '0',
  "editDate" timestamp DEFAULT NULL
);
INSERT INTO "ipaddresses" VALUES (1,1,'167837697','test ip #1','test-ip-1','','','1',0,'','','NULL','0','NULL');
INSERT INTO "ipaddresses" VALUES (2,1,'167837698','test ip #2','test-ip-2','','','1',0,'','','NULL','0','NULL');
INSERT INTO "ipaddresses" VALUES (3,1,'167837699','test ip #3','test-ip-3','','','1',0,'','','NULL','0','NULL');
INSERT INTO "ipaddresses" VALUES (4,1,'167837703','test ip #4','test-ip-4','','','1',0,'','','NULL','0','NULL');
INSERT INTO "ipaddresses" VALUES (5,1,'167837704','test ip #5','test-ip-5','','','1',0,'','','NULL','0','NULL');
INSERT INTO "ipaddresses" VALUES (6,1,'167837705','test ip #6','test-ip-6','','','1',0,'','','NULL','0','NULL');
INSERT INTO "ipaddresses" VALUES (7,1,'167837706','test ip #7','test-ip-7','','','1',0,'','','NULL','0','NULL');
CREATE TABLE "sections" (
  "id" int(11) NOT NULL ,
  "name" varchar(128) NOT NULL DEFAULT '',
  "description" text,
  "masterSection" int(11) DEFAULT '0',
  "permissions" varchar(1024) DEFAULT NULL,
  "strictMode" binary(1) NOT NULL DEFAULT '0',
  "subnetOrdering" varchar(16) DEFAULT NULL,
  "order" int(3) DEFAULT NULL,
  "editDate" timestamp DEFAULT NULL,
  "showVLAN" tinyint(1) NOT NULL DEFAULT '0',
  "showVRF" tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY ("name")
);
INSERT INTO "sections" VALUES (2,'Production','Section for Production Network',0,'{"2":"2","3":"1"}','1',NULL,NULL,NULL,0,0);
CREATE TABLE "vlans" (
  "vlanId" INTEGER PRIMARY_KEY,
  "name" varchar(255) NOT NULL,
  "number" int(4) DEFAULT NULL,
  "description" text NOT NULL,
  "editDate" timestamp DEFAULT NULL
);
INSERT INTO "vlans" VALUES (10,'test-vlan',42,'test-vlan desc',NULL);
CREATE TABLE "subnets" (
  "id" INTEGER PRIMARY KEY,
  "subnet" varchar(255) NOT NULL,
  "mask" varchar(255) NOT NULL,
  "sectionId" int(11)  DEFAULT NULL,
  "description" text NOT NULL,
  "vrfId" int(11)  DEFAULT NULL,
  "masterSubnetId" int(11)  DEFAULT NULL,
  "allowRequests" tinyint(1) DEFAULT '0',
  "vlanId" int(11)  DEFAULT NULL,
  "showName" tinyint(1) DEFAULT '0',
  "permissions" varchar(1024) DEFAULT NULL,
  "pingSubnet" tinyint(1) DEFAULT '0',
  "isFolder" tinyint(1) DEFAULT '0',
  "editDate" timestamp DEFAULT NULL
);
INSERT INTO "subnets" VALUES (1,'167837696','28',2,'TEST /28 SUBNET',0,0,1,10,0,'{"2":"1","3":"1"}',0,0,NULL);
CREATE INDEX "subnets_subnet" ON "subnets" ("subnet");
CREATE INDEX "sections_id" ON "sections" ("id");
CREATE INDEX "ipaddresses_dns_name" ON "ipaddresses" ("dns_name");
CREATE INDEX "ipaddresses_ip_addr" ON "ipaddresses" ("ip_addr");
CREATE INDEX "ipaddresses_description" ON "ipaddresses" ("description");
CREATE INDEX "ipaddresses_subnetid" ON "ipaddresses" ("subnetId");
END TRANSACTION;
