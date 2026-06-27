import pandas as pd

df = pd.read_csv('output.csv')

def fraud_score(row):
    score = 0
    flags = str(row['risk_flags']).split(';')
    
    # Image manipulation signals
    if 'possible_manipulation' in flags: score += 25
    if 'non_original_image' in flags: score += 20
    if 'text_instruction_present' in flags: score += 20
    
    # Mismatch signals
    if 'claim_mismatch' in flags: score += 15
    if 'wrong_object' in flags: score += 10
    if 'wrong_object_part' in flags: score += 10
    
    # History risk
    if 'user_history_risk' in flags: score += 15
    
    # Image quality (less suspicious, more operational)
    if 'blurry_image' in flags: score += 5
    if 'damage_not_visible' in flags: score += 5
    
    # Verdict signals
    if row['claim_status'] == 'contradicted': score += 20
    if row['evidence_standard_met'] == 'false': score += 5
    
    return min(score, 100)

def confidence(row):
    flags = str(row['risk_flags']).split(';')
    score = 100
    
    if row['evidence_standard_met'] == 'false': score -= 30
    if row['valid_image'] == 'false': score -= 20
    if 'blurry_image' in flags: score -= 10
    if 'wrong_angle' in flags: score -= 10
    if 'cropped_or_obstructed' in flags: score -= 10
    if 'low_light_or_glare' in flags: score -= 10
    if row['claim_status'] == 'not_enough_information': score -= 20
    if 'manual_review_required' in flags: score -= 10
    
    return max(score, 5)

def detect_language(text):
    hindi_chars = set('अआइईउऊएऐओऔकखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह')
    if any(c in hindi_chars for c in str(text)):
        return 'hi'
    hinglish_markers = ['meri', 'hai', 'kar', 'aap', 'mein', 'hua', 'gaya', 'kiya', 'nahi', 'tha']
    text_lower = str(text).lower()
    if any(word in text_lower for word in hinglish_markers):
        return 'hi-en'
    return 'en'

df['fraud_risk_score'] = df.apply(fraud_score, axis=1)
df['confidence_score'] = df.apply(confidence, axis=1)
df['claim_language'] = df['user_claim'].apply(detect_language)

df.to_csv('output.csv', index=False)

print('Done!')
print(df[['user_id', 'claim_status', 'fraud_risk_score', 'confidence_score', 'claim_language']].to_string())