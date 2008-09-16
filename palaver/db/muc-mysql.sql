BEGIN;
CREATE TABLE `muc_users` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `username` varchar(255) NOT NULL,
    `nick` varchar(255) ,
    `presence` longtext ,
    `resource` varchar(255) 
);
CREATE TABLE `muc_rooms` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `name` varchar(255) NOT NULL,
    `roomname` varchar(255) ,
    `subject` varchar(255) ,
    `subject_change` bool ,
    `persistent` bool ,
    `moderated` bool ,
    `private` bool ,
    `history` integer ,
    `game` bool ,
    `invitation` bool ,
    `invites` bool ,
    `hidden` bool ,
    `locked` bool ,
    `subjectlocked` bool ,
    `description` longtext ,
    `leave` varchar(255) ,
    `join` varchar(255) ,
    `rename` varchar(255) ,
    `maxusers` integer ,
    `privmsg` bool ,
    `change_nick` bool ,
    `query_occupants` bool ,
    UNIQUE (`name`)
);
CREATE TABLE `muc_roomattributess` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `room_id` integer NOT NULL REFERENCES `muc_rooms` (`id`),
    `key` varchar(255) NOT NULL,
    `value` longtext ,
    UNIQUE (`room_id`, `key`)
);
CREATE TABLE `muc_rooms_owners` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `room_id` integer NOT NULL REFERENCES `muc_rooms` (`id`),
    `user_id` integer NOT NULL REFERENCES `muc_users` (`id`),
    UNIQUE (`room_id`, `user_id`)
);
CREATE TABLE `muc_rooms_members` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `room_id` integer NOT NULL REFERENCES `muc_rooms` (`id`),
    `user_id` integer NOT NULL REFERENCES `muc_users` (`id`),
    UNIQUE (`room_id`, `user_id`)
);
CREATE TABLE `muc_rooms_admins` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `room_id` integer NOT NULL REFERENCES `muc_rooms` (`id`),
    `user_id` integer NOT NULL REFERENCES `muc_users` (`id`),
    UNIQUE (`room_id`, `user_id`)
);
CREATE TABLE `muc_rooms_outcasts` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `room_id` integer NOT NULL REFERENCES `muc_rooms` (`id`),
    `user_id` integer NOT NULL REFERENCES `muc_users` (`id`),
    UNIQUE (`room_id`, `user_id`)
);
CREATE TABLE `muc_rooms_roster` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `room_id` integer NOT NULL REFERENCES `muc_rooms` (`id`),
    `user_id` integer NOT NULL REFERENCES `muc_users` (`id`),
    UNIQUE (`room_id`, `user_id`)
);

COMMIT;
