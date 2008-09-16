alter table muc_rooms_roster add column user_jid varchar(255);
alter table muc_rooms_admins add column user_jid varchar(255);
alter table muc_rooms_owners add column user_jid varchar(255);
alter table muc_rooms_players add column user_jid varchar(255);
alter table muc_rooms_outcasts add column user_jid varchar(255);
alter table muc_rooms_members add column user_jid varchar(255);


alter table muc_rooms_admins add column actor varchar(255);
alter table muc_rooms_owners add column actor varchar(255);
alter table muc_rooms_players add column actor varchar(255);
alter table muc_rooms_outcasts add column actor varchar(255);
alter table muc_rooms_members add column actor varchar(255);

