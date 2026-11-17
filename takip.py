from datetime import datetime, timedelta, timezone
import json
import os
import re
from playwright.sync_api import sync_playwright
import requests

TAKIP_URL = "https://optimi.gg/battlepass-leaderboard"
NTFY_KANAL_ADI = os.environ.get("NTFY_KANAL_ADI", "")
TAKIP_LIMITI = 30
IZIN_VERILEN_ARTISLAR = (10, 20)
VERI_DOSYASI = "puanlar.json"
TR_SAAT_DILIMI = timezone(timedelta(hours=3))


def su_anki_zaman_metni():
  return datetime.now(TR_SAAT_DILIMI).strftime("%Y-%m-%d %H:%M:%S")


def su_anki_saat():
  return datetime.now(TR_SAAT_DILIMI).strftime("%H:%M:%S")


def xp_sayiya_cevir(xp_metni):
  sadece_rakamlar = re.sub(r"[^\d]", "", str(xp_metni))
  return int(sadece_rakamlar) if sadece_rakamlar else None


def telefona_bildirim_gonder(kullanici, sira, eski, yeni, artis):
  if not NTFY_KANAL_ADI:
    print("Hata: NTFY_KANAL_ADI gizli değişkeni bulunamadı!")
    return
  saat = su_anki_saat()
  mesaj = (
      f"[{saat}] #{sira} {kullanici} +{artis} XP kazandı! ({eski} -> {yeni} XP)"
  )
  requests.post(
      f"https://ntfy.sh/{NTFY_KANAL_ADI}",
      data=mesaj.encode("utf-8"),
      headers={
          "Title": f"{kullanici} (+{artis} XP) - {saat}",
          "Priority": "high",
          "Tags": "bell",
      },
      timeout=10,
  )
  print(f"[BİLDİRİM GÖNDERİLDİ] {mesaj}")


def guncel_listeyi_cek():
  with sync_playwright() as p:
    tarayici = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    baglam = tarayici.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 1080},
    )
    sayfa = baglam.new_page()
    sayfa.goto(TAKIP_URL, wait_until="domcontentloaded", timeout=60000)
    sayfa.wait_for_selector("text=XP", timeout=25000)

    sayfa.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    sayfa.wait_for_timeout(1500)

    sayfa_metni = sayfa.inner_text("body")
    tarayici.close()

  parcalar = [s.strip() for s in re.split(r"[\r\n\t]+", sayfa_metni) if s.strip()]
  sonuc = []
  gorulenler = set()

  for i, parca in enumerate(parcalar):
    kullanici = None
    xp = None

    tek_xp = re.match(r"^([\d\.]+)\s*XP$", parca, re.IGNORECASE)
    if tek_xp and i > 0:
      xp = xp_sayiya_cevir(tek_xp.group(1))
      kullanici = parcalar[i - 1]
    else:
      ayni_satir = re.match(r"^(.+?)\s+([\d\.]+)\s*XP$", parca, re.IGNORECASE)
      if ayni_satir:
        kullanici = ayni_satir.group(1).strip()
        xp = xp_sayiya_cevir(ayni_satir.group(2))

    if kullanici and xp is not None and kullanici not in gorulenler:
      gorulenler.add(kullanici)
      sonuc.append((kullanici, xp))

  return sonuc


def main():
  tum_liste = guncel_listeyi_cek()
  if not tum_liste:
    print(f"[{su_anki_saat()}] Uyarı: Sayfa açıldı ancak XP listesi okunamadı.")
    return

  ilk_30 = tum_liste[:TAKIP_LIMITI]
  eski_tablo = {}

  if os.path.exists(VERI_DOSYASI):
    with open(VERI_DOSYASI, "r", encoding="utf-8") as f:
      okunan = json.load(f)
      if isinstance(okunan, dict) and "ilk_30_tablosu" in okunan:
        eski_tablo = okunan["ilk_30_tablosu"]

  if not eski_tablo:
    print(
        f"[{su_anki_saat()}] İlk çalışma: {len(ilk_30)} kişilik tablo"
        " oluşturuldu."
    )
    for sira, (kullanici, xp) in enumerate(ilk_30, start=1):
      print(f"  #{sira} {kullanici}: {xp} XP")
  else:
    for sira, (kullanici, yeni_xp) in enumerate(ilk_30, start=1):
      if kullanici in eski_tablo:
        eski_xp = eski_tablo[kullanici]["xp"]
        fark = yeni_xp - eski_xp

        if fark in IZIN_VERILEN_ARTISLAR:
          telefona_bildirim_gonder(kullanici, sira, eski_xp, yeni_xp, fark)
        elif fark != 0:
          print(
              f"[{su_anki_saat()}] Filtre dışı değişim: #{sira} {kullanici}"
              f" ({fark:+} XP) -> {yeni_xp} XP"
          )

  yeni_durum = {
      "son_guncelleme": su_anki_zaman_metni(),
      "ilk_30_tablosu": {
          kullanici: {"sira": sira, "xp": xp}
          for sira, (kullanici, xp) in enumerate(ilk_30, start=1)
      },
  }
  with open(VERI_DOSYASI, "w", encoding="utf-8") as f:
    json.dump(yeni_durum, f, ensure_ascii=False, indent=2)

  print(
      f"[{su_anki_saat()}] Kontrol tamamlandı ve ilk {len(ilk_30)} tablosu"
      " güncellendi."
  )


if __name__ == "__main__":
  main()
