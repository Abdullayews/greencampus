import json
import re
import requests
from flask import session, request, jsonify
from config import get_db_connection

def ai_handler_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "İcazə yoxdur. Zəhmət olmasa daxil olun."})
    
    conn = get_db_connection()
    if isinstance(conn, tuple):
        return conn
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT api_key, ad_soyad FROM students WHERE id = %s", (session['user_id'],))
            user_data = cursor.fetchone()
    finally:
        conn.close()
    
    api_key = user_data.get('api_key', '') if user_data else ''
    istifadeci_adi = user_data.get('ad_soyad', 'Tələbə') if user_data else 'Tələbə'
    
    if not api_key:
        return jsonify({"success": False, "message": "API açarı tapılmadı! Zəhmət olmasa Profil bölməsindən şəxsi Gemini API açarınızı daxil edin."})
    
    data = request.get_json() or {}
    if not data or 'type' not in data:
        return jsonify({"success": False, "message": "Yanlış sorğu formatı."})
    
    model = "gemini-3.1-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    contents = []
    system_prompt = ""
    req_type = data['type']
    
    if req_type == 'chat':
        system_prompt = f"Sən 'Yaşıl Kampus' adlı Qarabağ Universitetinin yataqxanasının rəqəmsal AI köməkçisən. Adın 'Kampus AI'-dır. İstifadəçinin adı: {istifadeci_adi}. Əgər söhbət artıq başlayıbsa, təkrar Salam vermə, birbaşa cavab ver."
        
        history = data.get('history', [])
        for msg in history:
            role = 'user' if msg.get('role') == 'user' else 'model'
            contents.append({"role": role, "parts": [{"text": msg.get('text', '')}]})
        
        current_msg = (data.get('message') or '').strip()
        if not current_msg:
            return jsonify({"success": False, "message": "Boş mesaj göndərilə bilməz."})
        contents.append({"role": "user", "parts": [{"text": current_msg}]})
        temperature = 0.7
        max_tokens = 250
        
    elif req_type == 'match':
        system_prompt = "Sən bir uyğunluq hesablama aparatısan. İstifadəçiyə yalnız 0 ilə 100 arasında tam rəqəm qaytarırsan."
        target_id = data.get('target_id', 0)
        
        conn = get_db_connection()
        if isinstance(conn, tuple):
            return conn
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT s.id, s.ad_soyad, p.yuxu_rejimi, p.temizlik, p.sosial_munasibet, p.hayat_terzi 
                    FROM students s 
                    LEFT JOIN students_profiles p ON s.id = p.student_id 
                    WHERE s.id IN (%s, %s)
                """, (session['user_id'], target_id))
                users = cursor.fetchall()
        finally:
            conn.close()
        
        if len(users) < 2:
            return jsonify({"success": False, "message": "Tələbə məlumatları tapılmadı."})
        
        me = users[0]
        target = users[1]
        match_prompt = f"Tələbə 1 ({me['ad_soyad']}): Yuxu: {me['yuxu_rejimi']}, Təmizlik: {me['temizlik']}, Sosial: {me['sosial_munasibet']}, Həyat: {me['hayat_terzi']}.\n"
        match_prompt += f"Tələbə 2 ({target['ad_soyad']}): Yuxu: {target['yuxu_rejimi']}, Təmizlik: {target['temizlik']}, Sosial: {target['sosial_munasibet']}, Həyat: {target['hayat_terzi']}.\n"
        match_prompt += "Bu iki tələbənin otaq yoldaşı olaraq neçə faiz (0-100) uyğun olduğunu hesabla. Yalnız rəqəmi qaytar."
        
        contents.append({"role": "user", "parts": [{"text": match_prompt}]})
        temperature = 0.2
        max_tokens = 10
    else:
        return jsonify({"success": False, "message": "Yanlış sorğu növü."})
    
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.9
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        result = response.json()
    except Exception as e:
        return jsonify({"success": False, "message": "AI serverinə qoşulmaq mümkün olmadı."})
    
    if result.get('error'):
        return jsonify({"success": False, "message": f"AI Xətası: {result['error'].get('message', 'API açarı yanlış ola bilər!')}"})
    
    candidates = result.get('candidates', [])
    if not candidates or not candidates[0].get('content', {}).get('parts', [{}])[0].get('text'):
        return jsonify({"success": False, "message": "AI boş cavab qaytardı."})
    
    ai_text = candidates[0]['content']['parts'][0]['text']
    
    if req_type == 'match':
        numbers = re.findall(r'\d+', ai_text)
        score = int(numbers[0]) if numbers else 0
        score = max(0, min(100, score))
        return jsonify({"success": True, "score": score})
    else:
        return jsonify({"success": True, "reply": ai_text.strip()})