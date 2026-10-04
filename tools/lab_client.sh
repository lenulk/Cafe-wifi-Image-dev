#!/bin/bash
# lab_client.sh -- "ลูกค้าจำลอง" สำหรับทดสอบบน Pi จริงโดยไม่ต้องใช้มือถือ (ใช้ในแล็บเท่านั้น ต้องรันเป็น root)
#
# สร้าง network namespace + macvlan (bridge) บน eth0 ของ Pi เอง: มี MAC ของตัวเอง ขอ IP จาก dnsmasq
# และวิ่งผ่าน nftables + openNDS เหมือนอุปกรณ์จริงทุกขั้น (ใช้ทดสอบ 2 ต.ค. 2026 ดู
# docs/hardware-test-log.md §3.5) · ใช้ MAC แบบ locally administered (02:...) กันชนกับเครื่องจริง
#
#   lab_client.sh up cta 02:ca:fe:00:00:0a        # สร้างลูกค้า + ขอ DHCP
#   lab_client.sh login cta CAFE-XXXXX <password>  # เล่น portal ครบ: redirect -> login -> openNDS -> เน็ต
#   lab_client.sh run cta curl -s http://example.com/
#   lab_client.sh down cta                         # ลบทิ้ง (อย่าลืม: ndsctl deauth <mac>)
#
# ออกรหัสทดสอบผ่านหน้า /issue ตัวจริง: tools/lab_issue_voucher.py <เลขบัตร> <ชั่วโมง> <เครื่อง> [โควตา MB]
set -u
act=$1; ns=$2
case $act in
up)
  mac=$3
  ip netns add $ns
  ip link add link eth0 name ${ns}v type macvlan mode bridge
  # ลบ namespace เดิมแล้วสร้างใหม่ทันที macvlan เก่าที่มี MAC เดียวกันยังถูกลบไม่เสร็จ (async) -> ตั้ง MAC ไม่ได้
  # "Address already in use" แล้วลูกค้าจำลองได้ MAC สุ่ม ทดสอบทั้งชุดเพี้ยน (เจอ 2026-10-05) -> ลองซ้ำ
  for i in 1 2 3 4 5 6 7 8 9 10; do ip link set ${ns}v address $mac 2>/dev/null && break; sleep 1; done
  [ "$(cat /sys/class/net/${ns}v/address)" = "$(echo $mac | tr A-F a-f)" ] || { echo "$ns: ตั้ง MAC $mac ไม่ได้" >&2; ip link del ${ns}v; ip netns del $ns; exit 1; }
  ip link set ${ns}v netns $ns
  ip -n $ns link set lo up; ip -n $ns link set ${ns}v name eth0; ip -n $ns link set eth0 up
  mkdir -p /etc/netns/$ns
  cat > /tmp/udhcpc-$ns.sh <<S
#!/bin/sh
[ "\$1" = bound ] || [ "\$1" = renew ] || exit 0
ip addr flush dev \$interface; ip addr add \$ip/\${mask:-24} dev \$interface
ip route replace default via \$router
echo "nameserver \$dns" > /etc/netns/$ns/resolv.conf
echo "\$ip" > /tmp/client-$ns.ip
S
  chmod +x /tmp/udhcpc-$ns.sh
  ip netns exec $ns busybox udhcpc -i eth0 -x hostname:Lab-$ns-Phone -q -n -t 5 -s /tmp/udhcpc-$ns.sh >/dev/null 2>&1
  echo "$ns ip=$(cat /tmp/client-$ns.ip 2>/dev/null) mac=$mac" ;;
down)
  ip netns del $ns 2>/dev/null; rm -rf /etc/netns/$ns /tmp/udhcpc-$ns.sh /tmp/client-$ns.ip /tmp/cj-$ns; echo "$ns removed" ;;
run)
  shift 2; ip netns exec $ns "$@" ;;
login)
  code=$3; pw=$4; cj=/tmp/cj-$ns; rm -f $cj
  X="ip netns exec $ns curl -s -m 15 -b $cj -c $cj"
  loc=$($X -o /dev/null -w '%{redirect_url}' http://example.com/)
  echo "1 captive redirect -> ${loc:0:60}"
  page=$($X -L "$loc")
  nonce=$(echo "$page" | grep -o 'name="nonce" value="[^"]*"' | sed 's/.*value="//;s/"//')
  echo "2 login page nonce=${nonce:0:8}..."
  resp=$($X -o /tmp/resp-$ns -w '%{http_code} %{redirect_url}' --data-urlencode "nonce=$nonce" --data-urlencode "username=$code" --data-urlencode "password=$pw" "$(echo "$loc" | sed 's#\(http://[^/]*\)/.*#\1#')/login")
  echo "3 POST /login -> ${resp:0:90}"
  st=${resp%% *}; auth=${resp#* }
  if [ "$st" != 302 ]; then grep -o 'class="msg err[^"]*">[^<]*' /tmp/resp-$ns | sed 's/.*>//' ; exit 1; fi
  echo "4 openNDS auth -> $($X -o /dev/null -w '%{http_code}' "$auth")"
  sleep 1
  echo "5 internet -> $($X -o /dev/null -w '%{http_code}' http://example.com/)" ;;
esac
