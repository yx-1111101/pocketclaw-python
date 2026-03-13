-- Supabase SQL migration: normalize historical devices.box_id -> devices.device_id
-- Run in Supabase SQL Editor (single transaction).

begin;

-- 1) Backfill empty device_id from box_id (skip rows that would create duplicate device_id)
update devices d
set device_id = d.box_id
where (d.device_id is null or btrim(d.device_id) = '')
  and d.box_id is not null
  and btrim(d.box_id) <> ''
  and not exists (
    select 1
    from devices x
    where x.device_id = d.box_id
      and x.id <> d.id
  );

-- 2) Report unresolved rows (must be 0 before removing fallback in runtime)
--    unresolved原因通常是：box_id 为空，或与其他行 device_id 冲突。
select id, device_id, box_id
from devices
where device_id is null or btrim(device_id) = '';

commit;
