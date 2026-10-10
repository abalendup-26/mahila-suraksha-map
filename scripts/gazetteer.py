"""Place gazetteer for extracting city/district names from headlines/posts.
English names come from the NCRB district layer + common city aliases.
Devanagari names are a hand-written transliteration list of district/city names
(only place names - no incident data is invented here)."""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
GENERIC = {"central","central north","east","north","north east","north west","south","south east",
 "south west","west","outer north","old delhi","mon","mau","una","dhar","pali","tapi","patan","siang",
 "anand","kheda","narmada","gomati","bijapur","mandi","sagar","guna","durg","rewa","puri","kota",
 "banda","basti","gonda","etah","jind","moga","mansa","solan","leh ladakh","phek","peren","diu","daman",
 "nuh","sehore","raisen","harda","krishna","medak","dangs","khowai","kolar","hassan","gadag","bidar",
 "raigad","raigarh","korba","korea","sakti","balod","bastar","sukma","noney","senapati","mamit","wokha",
 "lohit","tirap","siaha","kamle","namsai","jalaun","kheri","saran","gaya","arwal","chandel","erode","nadia","panna","salem","jalna","malda","una","theni","bhind","mandla","seoni","pali","banka","buxar",
 "supaul","jamui","nawada","palamu","godda","pakur","dumka","khunti","chatra","garhwa","gumla","latehar"}
# Some of the GENERIC names are real districts that are also common words / ambiguous;
# they are still matched when written with a state or in Devanagari, or via the CITY list below.

CITY = {  # alias -> (display name, state)
 "delhi":("Delhi","Delhi"),"new delhi":("New Delhi","Delhi"),"noida":("Noida","Uttar Pradesh"),
 "greater noida":("Greater Noida","Uttar Pradesh"),"gurgaon":("Gurugram","Haryana"),"gurugram":("Gurugram","Haryana"),
 "bangalore":("Bengaluru","Karnataka"),"bengaluru":("Bengaluru","Karnataka"),"calcutta":("Kolkata","West Bengal"),
 "mumbai":("Mumbai","Maharashtra"),"bombay":("Mumbai","Maharashtra"),"navi mumbai":("Navi Mumbai","Maharashtra"),
 "chennai":("Chennai","Tamil Nadu"),"hyderabad":("Hyderabad","Telangana"),"secunderabad":("Secunderabad","Telangana"),
 "ahmedabad":("Ahmedabad","Gujarat"),"kanpur":("Kanpur","Uttar Pradesh"),"lucknow":("Lucknow","Uttar Pradesh"),
 "vizag":("Visakhapatnam","Andhra Pradesh"),"kochi":("Kochi","Kerala"),"cochin":("Kochi","Kerala"),
 "trivandrum":("Thiruvananthapuram","Kerala"),"mysore":("Mysuru","Karnataka"),"mangaluru":("Mangaluru","Karnataka"),
 "mangalore":("Mangaluru","Karnataka"),"allahabad":("Prayagraj","Uttar Pradesh"),"gwalior":("Gwalior","Madhya Pradesh"),
 "phagwara":("Phagwara","Punjab"),"pimpri":("Pimpri-Chinchwad","Maharashtra"),"aurangabad":("Chhatrapati Sambhajinagar","Maharashtra"),
 "ahmednagar":("Ahilyanagar","Maharashtra"),"belgaum":("Belagavi","Karnataka"),"gulbarga":("Kalaburagi","Karnataka"),
 "hubli":("Hubballi","Karnataka"),"hubballi":("Hubballi","Karnataka"),"jamshedpur":("Jamshedpur","Jharkhand"),
 "bhubaneswar":("Bhubaneswar","Odisha"),"guwahati":("Guwahati","Assam"),"shillong":("Shillong","Meghalaya"),
 "imphal":("Imphal","Manipur"),"agartala":("Agartala","Tripura"),"siliguri":("Siliguri","West Bengal"),
 "durgapur":("Durgapur","West Bengal"),"asansol":("Asansol","West Bengal"),"kota":("Kota","Rajasthan"),
 "durg":("Durg","Chhattisgarh"),"bhilai":("Bhilai","Chhattisgarh"),"coimbatore":("Coimbatore","Tamil Nadu"),
 "madurai":("Madurai","Tamil Nadu"),"trichy":("Tiruchirappalli","Tamil Nadu"),"vijayawada":("Vijayawada","Andhra Pradesh"),
 "nellore":("Nellore","Andhra Pradesh"),"kadapa":("Kadapa","Andhra Pradesh"),"anantapur":("Anantapur","Andhra Pradesh"),
 "warangal":("Warangal","Telangana"),"ludhiana":("Ludhiana","Punjab"),"mohali":("Mohali","Punjab"),
 "chandigarh":("Chandigarh","Chandigarh"),"panchkula":("Panchkula","Haryana"),"faridabad":("Faridabad","Haryana"),
 "ghaziabad":("Ghaziabad","Uttar Pradesh"),"meerut":("Meerut","Uttar Pradesh"),"jaipur":("Jaipur","Rajasthan"),
 "bhopal":("Bhopal","Madhya Pradesh"),"indore":("Indore","Madhya Pradesh"),"patna":("Patna","Bihar"),
 "ranchi":("Ranchi","Jharkhand"),"raipur":("Raipur","Chhattisgarh"),"dehradun":("Dehradun","Uttarakhand"),
 "srinagar":("Srinagar","Jammu And Kashmir"),"jammu":("Jammu","Jammu And Kashmir"),"goa":("Goa","Goa"),
 "panaji":("Panaji","Goa"),"thane":("Thane","Maharashtra"),"pune":("Pune","Maharashtra"),"nagpur":("Nagpur","Maharashtra"),
 "nashik":("Nashik","Maharashtra"),"surat":("Surat","Gujarat"),"vadodara":("Vadodara","Gujarat"),"baroda":("Vadodara","Gujarat"),
 "rajkot":("Rajkot","Gujarat"),"kolkata":("Kolkata","West Bengal"),"howrah":("Howrah","West Bengal"),
 "varanasi":("Varanasi","Uttar Pradesh"),"agra":("Agra","Uttar Pradesh"),"bareilly":("Bareilly","Uttar Pradesh"),
 "cuttack":("Cuttack","Odisha"),"kozhikode":("Kozhikode","Kerala"),"calicut":("Kozhikode","Kerala"),
 "thrissur":("Thrissur","Kerala"),"bastar":("Bastar","Chhattisgarh"),"gaya":("Gaya","Bihar"),"nuh":("Nuh","Haryana"),
 "mewat":("Nuh","Haryana"),"gonda":("Gonda","Uttar Pradesh"),"basti":("Basti","Uttar Pradesh"),"banda":("Banda","Uttar Pradesh"),
 "rewa":("Rewa","Madhya Pradesh"),
 "korba":("Korba","Chhattisgarh"),"raigarh":("Raigarh","Chhattisgarh"),"bilaspur":("Bilaspur","Chhattisgarh"),
}

HI = {  # Devanagari -> (display name, state)
 "दिल्ली":("Delhi","Delhi"),"नई दिल्ली":("New Delhi","Delhi"),"नोएडा":("Noida","Uttar Pradesh"),"ग्रेटर नोएडा":("Greater Noida","Uttar Pradesh"),
 "गाजियाबाद":("Ghaziabad","Uttar Pradesh"),"गाज़ियाबाद":("Ghaziabad","Uttar Pradesh"),"गुरुग्राम":("Gurugram","Haryana"),"गुड़गांव":("Gurugram","Haryana"),
 "फरीदाबाद":("Faridabad","Haryana"),"मेरठ":("Meerut","Uttar Pradesh"),"हापुड़":("Hapur","Uttar Pradesh"),"बुलंदशहर":("Bulandshahr","Uttar Pradesh"),
 "अलीगढ़":("Aligarh","Uttar Pradesh"),"आगरा":("Agra","Uttar Pradesh"),"मथुरा":("Mathura","Uttar Pradesh"),"हाथरस":("Hathras","Uttar Pradesh"),
 "कासगंज":("Kasganj","Uttar Pradesh"),"एटा":("Etah","Uttar Pradesh"),"मैनपुरी":("Mainpuri","Uttar Pradesh"),"फिरोजाबाद":("Firozabad","Uttar Pradesh"),
 "इटावा":("Etawah","Uttar Pradesh"),"औरैया":("Auraiya","Uttar Pradesh"),"कानपुर देहात":("Kanpur Dehat","Uttar Pradesh"),"कानपुर":("Kanpur","Uttar Pradesh"),
 "लखनऊ":("Lucknow","Uttar Pradesh"),"उन्नाव":("Unnao","Uttar Pradesh"),"रायबरेली":("Rae Bareli","Uttar Pradesh"),"अमेठी":("Amethi","Uttar Pradesh"),
 "सुल्तानपुर":("Sultanpur","Uttar Pradesh"),"अयोध्या":("Ayodhya","Uttar Pradesh"),"बाराबंकी":("Bara Banki","Uttar Pradesh"),"सीतापुर":("Sitapur","Uttar Pradesh"),
 "हरदोई":("Hardoi","Uttar Pradesh"),"लखीमपुर":("Lakhimpur Kheri","Uttar Pradesh"),"शाहजहांपुर":("Shahjahanpur","Uttar Pradesh"),"बरेली":("Bareilly","Uttar Pradesh"),
 "पीलीभीत":("Pilibhit","Uttar Pradesh"),"बदायूं":("Budaun","Uttar Pradesh"),"रामपुर":("Rampur","Uttar Pradesh"),"मुरादाबाद":("Moradabad","Uttar Pradesh"),
 "संभल":("Sambhal","Uttar Pradesh"),"अमरोहा":("Amroha","Uttar Pradesh"),"बिजनौर":("Bijnor","Uttar Pradesh"),"मुजफ्फरनगर":("Muzaffarnagar","Uttar Pradesh"),
 "मुज़फ्फरनगर":("Muzaffarnagar","Uttar Pradesh"),"शामली":("Shamli","Uttar Pradesh"),"सहारनपुर":("Saharanpur","Uttar Pradesh"),"बागपत":("Baghpat","Uttar Pradesh"),
 "प्रयागराज":("Prayagraj","Uttar Pradesh"),"कौशांबी":("Kaushambi","Uttar Pradesh"),"प्रतापगढ़":("Pratapgarh","Uttar Pradesh"),"फतेहपुर":("Fatehpur","Uttar Pradesh"),
 "बांदा":("Banda","Uttar Pradesh"),"चित्रकूट":("Chitrakoot","Uttar Pradesh"),"हमीरपुर":("Hamirpur","Uttar Pradesh"),"महोबा":("Mahoba","Uttar Pradesh"),
 "झांसी":("Jhansi","Uttar Pradesh"),"ललितपुर":("Lalitpur","Uttar Pradesh"),"जालौन":("Jalaun","Uttar Pradesh"),"वाराणसी":("Varanasi","Uttar Pradesh"),
 "जौनपुर":("Jaunpur","Uttar Pradesh"),"गाजीपुर":("Ghazipur","Uttar Pradesh"),"बलिया":("Ballia","Uttar Pradesh"),"आजमगढ़":("Azamgarh","Uttar Pradesh"),
 "मऊ":("Mau","Uttar Pradesh"),"मिर्जापुर":("Mirzapur","Uttar Pradesh"),"सोनभद्र":("Sonbhadra","Uttar Pradesh"),"भदोही":("Bhadohi","Uttar Pradesh"),
 "चंदौली":("Chandauli","Uttar Pradesh"),"गोरखपुर":("Gorakhpur","Uttar Pradesh"),"देवरिया":("Deoria","Uttar Pradesh"),"कुशीनगर":("Kushinagar","Uttar Pradesh"),
 "महराजगंज":("Mahrajganj","Uttar Pradesh"),"बस्ती":("Basti","Uttar Pradesh"),"सिद्धार्थनगर":("Siddharthnagar","Uttar Pradesh"),"गोंडा":("Gonda","Uttar Pradesh"),
 "बहराइच":("Bahraich","Uttar Pradesh"),"श्रावस्ती":("Shrawasti","Uttar Pradesh"),"बलरामपुर":("Balrampur","Uttar Pradesh"),"फर्रुखाबाद":("Farrukhabad","Uttar Pradesh"),
 "कन्नौज":("Kannauj","Uttar Pradesh"),"अंबेडकरनगर":("Ambedkar Nagar","Uttar Pradesh"),"संत कबीर नगर":("Sant Kabir Nagar","Uttar Pradesh"),
 "जयपुर":("Jaipur","Rajasthan"),"अलवर":("Alwar","Rajasthan"),"भरतपुर":("Bharatpur","Rajasthan"),"धौलपुर":("Dholpur","Rajasthan"),"करौली":("Karauli","Rajasthan"),
 "दौसा":("Dausa","Rajasthan"),"टोंक":("Tonk","Rajasthan"),"अजमेर":("Ajmer","Rajasthan"),"कोटा":("Kota","Rajasthan"),"बूंदी":("Bundi","Rajasthan"),
 "जोधपुर":("Jodhpur","Rajasthan"),"उदयपुर":("Udaipur","Rajasthan"),"बीकानेर":("Bikaner","Rajasthan"),"सीकर":("Sikar","Rajasthan"),"झुंझुनूं":("Jhunjhunu","Rajasthan"),
 "चूरू":("Churu","Rajasthan"),"नागौर":("Nagaur","Rajasthan"),"पाली":("Pali","Rajasthan"),"बाड़मेर":("Barmer","Rajasthan"),"जैसलमेर":("Jaisalmer","Rajasthan"),
 "भीलवाड़ा":("Bhilwara","Rajasthan"),"चित्तौड़गढ़":("Chittorgarh","Rajasthan"),"बांसवाड़ा":("Banswara","Rajasthan"),"डूंगरपुर":("Dungarpur","Rajasthan"),
 "श्रीगंगानगर":("Ganganagar","Rajasthan"),"हनुमानगढ़":("Hanumangarh","Rajasthan"),"सवाई माधोपुर":("Sawai Madhopur","Rajasthan"),"झालावाड़":("Jhalawar","Rajasthan"),
 "भोपाल":("Bhopal","Madhya Pradesh"),"इंदौर":("Indore","Madhya Pradesh"),"उज्जैन":("Ujjain","Madhya Pradesh"),"ग्वालियर":("Gwalior","Madhya Pradesh"),
 "जबलपुर":("Jabalpur","Madhya Pradesh"),"रीवा":("Rewa","Madhya Pradesh"),"सतना":("Satna","Madhya Pradesh"),
 "मुरैना":("Morena","Madhya Pradesh"),"भिंड":("Bhind","Madhya Pradesh"),"शिवपुरी":("Shivpuri","Madhya Pradesh"),
 "छतरपुर":("Chhatarpur","Madhya Pradesh"),"टीकमगढ़":("Tikamgarh","Madhya Pradesh"),"दमोह":("Damoh","Madhya Pradesh"),"कटनी":("Katni","Madhya Pradesh"),
 "देवास":("Dewas","Madhya Pradesh"),"रतलाम":("Ratlam","Madhya Pradesh"),"मंदसौर":("Mandsaur","Madhya Pradesh"),
 "खरगोन":("Khargone","Madhya Pradesh"),"खंडवा":("Khandwa","Madhya Pradesh"),"विदिशा":("Vidisha","Madhya Pradesh"),"सीहोर":("Sehore","Madhya Pradesh"),
 "रायसेन":("Raisen","Madhya Pradesh"),"छिंदवाड़ा":("Chhindwara","Madhya Pradesh"),"बैतूल":("Betul","Madhya Pradesh"),"शहडोल":("Shahdol","Madhya Pradesh"),
 "सिंगरौली":("Singrauli","Madhya Pradesh"),"सीधी":("Sidhi","Madhya Pradesh"),"नर्मदापुरम":("Narmadapuram","Madhya Pradesh"),"होशंगाबाद":("Narmadapuram","Madhya Pradesh"),
 "पटना":("Patna","Bihar"),"मुजफ्फरपुर":("Muzaffarpur","Bihar"),"भागलपुर":("Bhagalpur","Bihar"),"दरभंगा":("Darbhanga","Bihar"),
 "बेगूसराय":("Begusarai","Bihar"),"समस्तीपुर":("Samastipur","Bihar"),"वैशाली":("Vaishali","Bihar"),"नालंदा":("Nalanda","Bihar"),"सारण":("Saran","Bihar"),
 "छपरा":("Chhapra","Bihar"),"सीवान":("Siwan","Bihar"),"गोपालगंज":("Gopalganj","Bihar"),"मोतिहारी":("Motihari","Bihar"),"बेतिया":("Bettiah","Bihar"),
 "सीतामढ़ी":("Sitamarhi","Bihar"),"मधुबनी":("Madhubani","Bihar"),"पूर्णिया":("Purnia","Bihar"),"कटिहार":("Katihar","Bihar"),"अररिया":("Araria","Bihar"),
 "किशनगंज":("Kishanganj","Bihar"),"सहरसा":("Saharsa","Bihar"),"मधेपुरा":("Madhepura","Bihar"),"सुपौल":("Supaul","Bihar"),"मुंगेर":("Munger","Bihar"),
 "जमुई":("Jamui","Bihar"),"नवादा":("Nawada","Bihar"),"औरंगाबाद":("Aurangabad","Bihar"),"रोहतास":("Rohtas","Bihar"),"सासाराम":("Sasaram","Bihar"),
 "भोजपुर":("Bhojpur","Bihar"),"बक्सर":("Buxar","Bihar"),"जहानाबाद":("Jehanabad","Bihar"),"खगड़िया":("Khagaria","Bihar"),
 "रांची":("Ranchi","Jharkhand"),"धनबाद":("Dhanbad","Jharkhand"),"जमशेदपुर":("Jamshedpur","Jharkhand"),"बोकारो":("Bokaro","Jharkhand"),"हजारीबाग":("Hazaribagh","Jharkhand"),
 "गिरिडीह":("Giridih","Jharkhand"),"देवघर":("Deoghar","Jharkhand"),"दुमका":("Dumka","Jharkhand"),"पलामू":("Palamu","Jharkhand"),
 "रायपुर":("Raipur","Chhattisgarh"),"बिलासपुर":("Bilaspur","Chhattisgarh"),"दुर्ग":("Durg","Chhattisgarh"),"भिलाई":("Bhilai","Chhattisgarh"),"कोरबा":("Korba","Chhattisgarh"),
 "रायगढ़":("Raigarh","Chhattisgarh"),"सरगुजा":("Surguja","Chhattisgarh"),"अंबिकापुर":("Ambikapur","Chhattisgarh"),"जगदलपुर":("Jagdalpur","Chhattisgarh"),
 "राजनांदगांव":("Rajnandgaon","Chhattisgarh"),"धमतरी":("Dhamtari","Chhattisgarh"),"महासमुंद":("Mahasamund","Chhattisgarh"),
 "देहरादून":("Dehradun","Uttarakhand"),"हरिद्वार":("Haridwar","Uttarakhand"),"नैनीताल":("Nainital","Uttarakhand"),"हल्द्वानी":("Haldwani","Uttarakhand"),
 "ऊधमसिंह नगर":("Udham Singh Nagar","Uttarakhand"),"रुद्रपुर":("Rudrapur","Uttarakhand"),"अल्मोड़ा":("Almora","Uttarakhand"),
 "चंडीगढ़":("Chandigarh","Chandigarh"),"पंचकूला":("Panchkula","Haryana"),"अंबाला":("Ambala","Haryana"),"करनाल":("Karnal","Haryana"),"पानीपत":("Panipat","Haryana"),
 "सोनीपत":("Sonipat","Haryana"),"रोहतक":("Rohtak","Haryana"),"हिसार":("Hisar","Haryana"),"भिवानी":("Bhiwani","Haryana"),"जींद":("Jind","Haryana"),
 "कैथल":("Kaithal","Haryana"),"कुरुक्षेत्र":("Kurukshetra","Haryana"),"यमुनानगर":("Yamunanagar","Haryana"),"सिरसा":("Sirsa","Haryana"),"रेवाड़ी":("Rewari","Haryana"),
 "पलवल":("Palwal","Haryana"),"नूंह":("Nuh","Haryana"),"झज्जर":("Jhajjar","Haryana"),"फतेहाबाद":("Fatehabad","Haryana"),
 "लुधियाना":("Ludhiana","Punjab"),"अमृतसर":("Amritsar","Punjab"),"जालंधर":("Jalandhar","Punjab"),"पटियाला":("Patiala","Punjab"),"बठिंडा":("Bathinda","Punjab"),
 "मोहाली":("Mohali","Punjab"),"फगवाड़ा":("Phagwara","Punjab"),"शिमला":("Shimla","Himachal Pradesh"),"कांगड़ा":("Kangra","Himachal Pradesh"),
 "मुंबई":("Mumbai","Maharashtra"),"पुणे":("Pune","Maharashtra"),"नागपुर":("Nagpur","Maharashtra"),"ठाणे":("Thane","Maharashtra"),"नासिक":("Nashik","Maharashtra"),
 "अहमदाबाद":("Ahmedabad","Gujarat"),"सूरत":("Surat","Gujarat"),"वडोदरा":("Vadodara","Gujarat"),"राजकोट":("Rajkot","Gujarat"),
 "कोलकाता":("Kolkata","West Bengal"),"हावड़ा":("Howrah","West Bengal"),"बेंगलुरु":("Bengaluru","Karnataka"),"हैदराबाद":("Hyderabad","Telangana"),
 "चेन्नई":("Chennai","Tamil Nadu"),"भुवनेश्वर":("Bhubaneswar","Odisha"),"कटक":("Cuttack","Odisha"),"गुवाहाटी":("Guwahati","Assam"),
 "जम्मू":("Jammu","Jammu And Kashmir"),"श्रीनगर":("Srinagar","Jammu And Kashmir"),"गोवा":("Goa","Goa"),
}

def load_english(geojson_path):
    g = {}
    for f in json.load(open(geojson_path))["features"]:
        p = f["properties"]; n = (p["dis"] or "").strip()
        if not n or n.lower() in GENERIC or len(n) < 4: continue
        g.setdefault(n.lower(), (n, p["state"]))
    g.update(CITY)
    return g

class Gazetteer:
    def __init__(self, geojson_path):
        self.en = load_english(geojson_path)
        keys = sorted(self.en, key=len, reverse=True)
        self.en_re = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", re.I)
        hk = sorted(HI, key=len, reverse=True)
        self.hi_re = re.compile("(" + "|".join(re.escape(k) for k in hk) + ")")
    def find(self, text):
        """Return list of (display, state, matched_text, position) in order of appearance."""
        out = []
        for m in self.en_re.finditer(text):
            d, s = self.en[m.group(1).lower()]; out.append((d, s, m.group(1), m.start()))
        for m in self.hi_re.finditer(text):
            d, s = HI[m.group(1)]; out.append((d, s, m.group(1), m.start()))
        out.sort(key=lambda x: x[3])
        return out
