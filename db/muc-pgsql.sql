BEGIN;
CREATE TABLE "muc_users" (
    "id" serial NOT NULL PRIMARY KEY,
    "username" varchar(255) NOT NULL,
    "presence" text ,
    "resource" varchar(255),
    UNIQUE ("username")
);
CREATE TABLE "muc_rooms" (
    "id" serial NOT NULL PRIMARY KEY,
    "name" varchar(255) NOT NULL,
    "roomname" varchar(255) ,
    "subject" varchar(255) ,
    "subject_change" boolean ,
    "persistent" boolean ,
    "moderated" boolean ,
    "private" boolean ,
    "history" integer ,
    "game" boolean ,
    "invitation" boolean ,
    "invites" boolean ,
    "hidden" boolean ,
    "locked" boolean ,
    "subjectlocked" boolean ,
    "description" text ,
    "leave" varchar(255) ,
    "join" varchar(255) ,
    "rename" varchar(255) ,
    "maxusers" integer ,
    "privmsg" boolean ,
    "change_nick" boolean ,
    "query_occupants" boolean,
    "hostname" varchar(255) NOT NULL, 
    UNIQUE ("name", "hostname")
);
CREATE TABLE "muc_roomattributess" (
    "id" serial NOT NULL PRIMARY KEY,
    "room_id" integer NOT NULL REFERENCES "muc_rooms" ("id") on delete cascade,
    "key" varchar(255) NOT NULL,
    "value" text ,
    UNIQUE ("room_id", "key")
);
CREATE TABLE "muc_rooms_owners" (
    "id" serial NOT NULL PRIMARY KEY,
    "room_id" integer NOT NULL REFERENCES "muc_rooms" ("id") on delete cascade,
    "user_id" integer NOT NULL REFERENCES "muc_users" ("id"),
    UNIQUE ("room_id", "user_id")
);
CREATE TABLE "muc_rooms_members" (
    "id" serial NOT NULL PRIMARY KEY,
    "room_id" integer NOT NULL REFERENCES "muc_rooms" ("id") on delete cascade,
    "user_id" integer NOT NULL REFERENCES "muc_users" ("id"),
    UNIQUE ("room_id", "user_id")
);

CREATE TABLE "muc_rooms_admins" (
    "id" serial NOT NULL PRIMARY KEY,
    "room_id" integer NOT NULL REFERENCES "muc_rooms" ("id") on delete cascade,
    "user_id" integer NOT NULL REFERENCES "muc_users" ("id"),
    UNIQUE ("room_id", "user_id")
);

CREATE TABLE "muc_rooms_players" (
    "id" serial NOT NULL PRIMARY KEY,
    "room_id" integer NOT NULL REFERENCES "muc_rooms" ("id") on delete cascade,
    "user_id" integer NOT NULL REFERENCES "muc_users" ("id"),
    UNIQUE ("room_id", "user_id")
);

CREATE TABLE "muc_rooms_outcasts" (
    "id" serial NOT NULL PRIMARY KEY,
    "room_id" integer NOT NULL REFERENCES "muc_rooms" ("id") on delete cascade,
    "user_id" integer NOT NULL REFERENCES "muc_users" ("id"),
    "reason" varchar(255) ,
    UNIQUE ("room_id", "user_id")
);

CREATE TABLE "muc_rooms_roster" (
    "id" serial NOT NULL PRIMARY KEY,
    "room_id" integer NOT NULL REFERENCES "muc_rooms" ("id") on delete cascade,
    "user_id" integer NOT NULL REFERENCES "muc_users" ("id"),
    "role" varchar(55) NULL,
    "affiliation" varchar(55) NULL,
    "nick" varchar(255) ,	 	
    "show" varchar(255) ,	 	
    "status" varchar(255) ,	 	
    "legacy" boolean ,	 	
    UNIQUE ("room_id", "user_id")
);

COMMIT;
