-- Supabase SQL migration: phone-first identity + idless key hardening.
-- Assumption: users/devices tables no longer have numeric id columns.
-- Run in Supabase SQL Editor.

begin;

-- 0) Normalize string keys.
update users
set user_id = btrim(user_id)
where user_id is not null
  and user_id <> btrim(user_id);

update users
set phone = btrim(phone)
where phone is not null
  and phone <> btrim(phone);

update users
set openid = btrim(openid)
where openid is not null
  and openid <> btrim(openid);

update devices
set device_id = btrim(device_id)
where device_id is not null
  and device_id <> btrim(device_id);

update device_bindings
set user_id = btrim(user_id),
    device_id = btrim(device_id)
where (user_id is not null and user_id <> btrim(user_id))
   or (device_id is not null and device_id <> btrim(device_id));

-- 1) Drop obviously invalid bindings.
delete from device_bindings
where user_id is null
   or device_id is null
   or btrim(user_id) = ''
   or btrim(device_id) = '';

delete from device_bindings b
where not exists (
    select 1 from users u where u.user_id = b.user_id
)
or not exists (
    select 1 from devices d where d.device_id = b.device_id
);

-- 2) De-duplicate repeated bindings (same user_id + device_id).
delete from device_bindings a
using device_bindings b
where a.ctid < b.ctid
  and a.user_id = b.user_id
  and a.device_id = b.device_id;

-- 3) Block migration when user_id/device_id/phone has duplicates.
do $$
begin
    if exists (
        select 1
        from users
        where user_id is null or btrim(user_id) = ''
    ) then
        raise exception 'users.user_id contains null/empty values';
    end if;

    if exists (
        select user_id
        from users
        group by user_id
        having count(*) > 1
    ) then
        raise exception 'duplicate users.user_id found';
    end if;

    if exists (
        select 1
        from devices
        where device_id is null or btrim(device_id) = ''
    ) then
        raise exception 'devices.device_id contains null/empty values';
    end if;

    if exists (
        select device_id
        from devices
        group by device_id
        having count(*) > 1
    ) then
        raise exception 'duplicate devices.device_id found';
    end if;

    if exists (
        select phone
        from users
        where phone is not null and btrim(phone) <> ''
        group by phone
        having count(*) > 1
    ) then
        raise exception 'duplicate users.phone found (clean duplicates before enforcing unique index)';
    end if;
end
$$;

-- 4) Enforce uniqueness and query performance for idless keys.
create unique index if not exists idx_users_user_id_unique
    on users(user_id);

create unique index if not exists idx_devices_device_id_unique
    on devices(device_id);

create unique index if not exists idx_users_phone_unique_not_empty
    on users(phone)
    where phone is not null and btrim(phone) <> '';

create unique index if not exists idx_device_bindings_user_device_unique
    on device_bindings(user_id, device_id);

create index if not exists idx_device_bindings_user_id
    on device_bindings(user_id);

create index if not exists idx_device_bindings_device_id
    on device_bindings(device_id);

commit;
