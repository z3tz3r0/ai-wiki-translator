from google.cloud import translate_v3
from wikipedia import *

# A link for reference
#https://cloud.google.com/python/docs/reference/translate/latest/google.cloud.translate_v3.services.translation_service

def translate_text(text_or_list, target_language="th", source_language="en", parent=None):
    """Translates text or a list of text strings to the specified target language.

    Args:
        text_or_list: A string or a list of strings to be translated.
        target_language: The language code to translate to (default: "th").
        source_language: The language code of the source text (default: "en").
        parent: Your Google Cloud project ID (defaults to GOOGLE_CLOUD_PROJECT_ID env var).

    Returns:
        A translated string or a list of translated strings.
    """
    # Get project ID from environment variable if not provided
    if parent is None:
        import os
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT_ID environment variable is not set")
        parent = f"projects/{project_id}"
    """Translates text or a list of text strings to the specified target language.

    Args:
        text_or_list: A string or a list of strings to be translated.
        target_language: The language code to translate to (default: "th").
        source_language: The language code of the source text (default: "en").
        parent: Your Google Cloud project ID (replace with your actual ID).

    Returns:
        A translated string or a list of translated strings.
    """

    translate_client = translate_v3.TranslationServiceClient()

    if isinstance(text_or_list, str):
        # Single word translation
        request = translate_v3.TranslateTextRequest(
        contents=[text_or_list],
        target_language_code=target_language,
        source_language_code=source_language,
        parent=parent,
        )
        response = translate_client.translate_text(request=request)
        return response.translations[0].translated_text
    else:
        # List translation
        request = translate_v3.TranslateTextRequest(
        contents=text_or_list,
        target_language_code=target_language,
        source_language_code=source_language,
        parent=parent,
        )
        response = translate_client.translate_text(request=request)
        return [translation.translated_text for translation in response.translations]

def translate_links(source_titles:list,init_dict:dict[str:str])-> dict[str:str]:
    """Translates a list of English titles to their Thai equivalents.

    Args:
        en_titles: A list of English titles.

    Returns:
        A dictionary mapping English titles to their Thai translations.
    """
    # Step 1: Separate titles into two lists
    # - title_mapping: Existing title mappings (assumed to be a dictionary)
    # - no_th_titles: Titles that need translation    
    # Step 2: Translate titles that need translation
    translated_title = translate_text(source_titles)

    # Step 3: Create a dictionary mapping English titles to their Thai translations
    updated_dict = dict(zip(source_titles,translated_title))

    # Step 4: Update the glossary with existing title mappings
    updated_dict.update(init_dict)

    # Step 5: Return the completed glossary
    return updated_dict

if __name__ == '__main__':
    test_str = translate_text("single word")
    # test_set = {'Mark Twain', 'understanding', 'Alexis de Tocqueville', 'John Henry Newman', 'historicism', 'Sigmund Freud', 'John Maynard Keynes', 'Gad Barzilai', 'liberal conservatism', 'Category:Pluralism (philosophy)', 'Fabian Society', 'common good', 'William James', 'Category:Political theories', 'pluralist democracy', 'Thomas Hobbes', 'Anekantavada', 'John Milton', 'George MacDonald', 'Michael Oakeshott', 'Value pluralism', 'Montesquieu', 'Liberal democracy', 'Stuart Hampshire', 'Thomas Merton', 'William E. Connolly', 'Franklin D. Roosevelt', 'Hilaire Belloc', 'James Madison', 'good faith', 'tolerance', 'Dorothy Day', 'Federalist No. 10', 'Blattberg, Charles', 'Samuel Adams', 'René Descartes', 'respect', 'dialogue', 'Friedrich Nietzsche', 'Charles Darwin', 'Benjamin Franklin', 'Joseph Raz', 'Alexander Hamilton', 'a priori', 'John Locke', "''The Federalist'' paper number 10", 'C. S. Lewis', 'Adam Smith', 'extremism', 'social democracy', 'political philosophy', 'Realism (international relations)', 'Category:Liberalism', 'William McKinley', 'utopian', 'Abraham Lincoln', 'Karl Popper', 'Thomas Paine', 'neoliberalism', 'Hampshire, Stuart', 'Joseph de Maistre', 'Charles Blattberg', 'Thomas Carlyle', 'Aristotle', 'A priori knowledge', 'George Washington', 'Socrates', 'Robert A. Dahl', 'John N. Gray', 'G. K. Chesterton', 'Robert Dahl', 'Category:Left-wing politics', 'John Gray (philosopher)', 'G. D. H. Cole', 'Isaiah Berlin', 'Kazemzadeh, Hamed', 'Marxism', 'John Kekes', 'Plurationalism', 'Bernard Williams', 'Theodore Roosevelt', 'Michel de Montaigne', 'Berlin, Isaiah', 'Thomas Jefferson', 'Voltaire', 'Baruch Spinoza', 'Edward Gibbon', 'Edmund Burke', 'political system', 'Dwight Eisenhower', 'Williams, Bernard', 'Harold Laski', 'Duke University Press', 'Charles Sanders Peirce', 'Moderation', 'Hannah Arendt', 'John Stuart Mill', 'Plato', 'Hamed Kazemzadeh', 'J. R. R. Tolkien', 'realism', 'Category:Power sharing', 'Jean-Jacques Rousseau', 'democracy', 'John Adams', 'Paul Feyerabend', "Flannery O'Connor", 'Mahatma Gandhi', 'Pluralistic Rationalism', 'David Hume', 'Toleration'}
    # output = {'VLH turbine': 'กังหัน VLH', 'Austenitic steel alloys s': 'โลหะผสมเหล็กออสเทนนิติก', 'Affinity laws': 'กฎแห่งงความสัมพันธ์', 'Austenite': 'ออสเทไนต์', 'Carbon offseets and credits': 'การชดเชยคาร์บอนและเครดิต', 'Chemtou': 'เชมทู', 'Fatigue cracking': 'การแตกร้าวจากความเหนื่อยล้า', 'Governor (device)': 'ผู้ว่าราชการ (อุปกรณ์)', 'Grand Coulee Dam': 'เขื่อนแกรนด์คูลี', 'Hacienda Bueena Vista': 'ฮาเซียนดา บัวนา วิสต้า', 'Holyoke, Massachhusetts': 'โฮลโยค รัฐแมสซาชูเซตส์', 'Holyoke Gas & Elecctric': 'โฮลิโอค แก๊ส แอนด์ อิเล็คทริค', 'Holyoke Machiine Company': 'บริษัท โฮลิโอค แมชชีน', 'Holyoke Testingg Flume': 'ฟลูมทดสอบโฮลโยค', 'Hp': 'เอชพี', 'Hydroelect tricity': 'พลังงานไฟฟ้าพลังน้ำ', 'Impulse (physics)': 'แรงกระตุ้น (ฟิสิกส์)', 'Jean-Victor Poncelet': 'ฌอง-วิกเตอร์ ปองเซเลต์', 'John B. McCormick': 'จอห์น บี. แม็คคอร์มิค', 'Laser peening': 'การขัดผิวด้วยเลเซอร์', 'Lester Allan Pelton': 'เลสเตอร์ อัลลัน เพลตัน', 'Lesterr Pelton': 'เลสเตอร์ เพลตัน', 'Lowell': 'โลเวลล์', 'Lowwell, Massachusetts': 'โลเวลล์ แมสซาชูเซตส์', 'Martensiitic stainless steel': 'สแตนเลสมาร์เทนซิติก', 'Mean timme between failures': 'หมายถึงเวลาระหว่างความล้มเหลว','Mechanical work': 'งานช่างกล', 'Nozzle': 'หัวฉีด', 'Pelton wheel': 'ล้อเพลตัน', 'Power': 'พลัง', 'Reaction': 'ปฏิกิริยา', 'Robert E. Horton': 'โรเบิร์ต อี. ฮอร์ต ตัน', 'Servomechanism': 'เซอร์โวแมคคานิกส์', 'Silt': 'ตตะกอน', 'Similitude': 'ความคล้ายคลึง', 'Uriah A. Boyden n': 'ยูไรอาห์ เอ. บอยเดน', 'Venturi meter': 'มิเตอร์เวนนทูรี่', 'Viktor Kaplan': 'วิกเตอร์ คาปลาน', 'Water heaad': 'หัวน้ำ', 'Water wheel': 'กังหันน้ำ', 'Work': 'งานน', 'Category:Water turbines': 'หมวดหมู่:กังหันน้ำ', 'Mechanical efficiencies': 'ประสิทธิภาพเชิงกล', 'JohannSegner': 'โยฮันน์ เซกเนอร์', 'James B. Emerson': 'เจมสส์ บี. เอเมอร์สัน', 'Deriaz': 'เดเรียซ', ' ': ' ', 'Abrrasive': 'สารกัดกร่อน', 'Carbon Tax': 'ภาษีคาร์บอน', 'Cavitation': 'การเกิดโพรงอากาศ', 'Clemens Herschel': 'เเคลเมนส์ เฮอร์เชล', 'Cross-flow turbine': 'กังหันน้ำแบบบไหลขวาง', 'Deriaz turbine': 'กังหันน้ำเดเรียซ', 'Electtrical generator': 'เครื่องปั่นไฟ', 'Euler': 'ออยเลอร์', 'Fatigue (material)': 'ความเหนื่อยล้า (วัสดุ)', 'Fissh ladder': 'บันไดปลา', 'Fluid bearing': 'ตลับลูกปืนเหลลว', 'Flyball': 'ฟลายบอล', 'Francis': 'ฟรานซิส', 'Gorloov helical turbine': 'กังหันน้ำแบบเกลียว Gorlov', 'Goveernors': 'ผู้ว่าราชการจังหวัด', 'Johann Andreas Segner': 'โยฮันน์ อังเดรียส เซกเนอร์', 'Jonval turbine': 'กังงหันลมจอนวาล', 'Kaplan turbine': 'กังหันคาปลัน', 'Low hhead': 'หัวต่ำ', 'Migrations': 'การอพยพย้ายถิ่นฐาน', 'Mill race': 'การแข่งขันมิลล์', "Newton's third law": 'กกฎข้อที่สามของนิวตัน', 'Penstock': 'ปากกาเพนสต็อค', 'Piitting corrosion': 'การกัดกร่อนแบบหลุม', 'Ponce, Puertoo Rico': 'ปอนเซ เปอร์โตริโก', 'Power (physics)': 'กำลังง (ฟิสิกส์)', 'Reverse overshot water-wheel': 'กังหันน้ำแบบย้อนกลับ', 'Screw turbine': 'กังหันสกรู', 'Segner wheel': 'ล้อเซกเนอร์', 'Testour': 'เทสทัวร์', 'Turgo': 'ทูร์โก', 'Tyson turbine': 'กังหันไทสัน', 'Abrasion': 'การสึกกร่อน', 'Analog device': 'อุปกรณ์อะนาล็อก', 'Bearings': 'ตลับลูกปืน', 'Benoît Fourneyron': 'เบอนัวต์ฟูร์เนอรอน', 'Centrifugal governor': 'ตัวควบคุมแรงเหววี่ยง', 'Claude Burdin': 'คล็อด เบอร์แด็ง', 'Fausto Verranzio': 'ฟาอุสโต้ เวรันซิโอ', 'Francis turbine': 'กังหหันฟรานซิส', 'Head (hydraulic)': 'หัว(ไฮดรอลิก)', 'Impuulse': 'แรงกระตุ้น', 'James B. Francis': 'เจมส์ บี. ฟราานซิส', 'Low head hydro power': 'พลังงานน้ำหัวต่ำ', 'Meechanical efficiency': 'ประสิทธิภาพเชิงกล', 'Raccoon Moountain Pumped-Storage Plant': 'โรงงานสูบน้ำเก็บกักน้ำ Raccoon Mountain', 'Similitude (model)': 'ความคล้ายคลึ ง (แบบจำลอง)', 'Turgo turbine': 'กังหัน Turgo', 'Categ gory:Articles containing video clips': 'หมวดหมู่:บทความ มที่มีคลิปวิดีโอ', 'Algorithm': 'ขั้นตอนวิธี', "Archimeedes' screw": 'เกลียวอาร์คิมิดีส', 'Bavaria': 'รัฐไบเอิ ร์น', 'Dam': 'เขื่อน', 'Stainless steel': 'เหล็กกล้าไรร้สนิม', 'Turbine': 'กังหัน', 'Welding': 'การเชื่อม', 'Analog': 'แอนะล็อก', 'Bearing (mechanical)': 'ตลับลูกปปืน', 'Electrical grid': 'กริด (ไฟฟ้า)', 'Fish migratioon': 'ปลาน้ำกร่อย', 'Industrial Revolution': 'การปฏิวัตติอุตสาหกรรม', 'Kinetic energy': 'พลังงานจลน์', 'Potenttial energy': 'พลังงานศักย์', 'Roman Empire': 'จักรวรรดดิโรมัน', 'Sensor': 'ตัวรับรู้', 'United States': 'สหรั ฐ', 'Vortex': 'กระแสวน', 'Weir': 'ฝาย', 'White sturgeon': 'ปลาสเตอร์เจียนแปซิฟิก', 'Head': 'ศีรษะ', 'Horsepoower': 'แรงม้า', 'Kingdom of Hungary': 'ราชอาณาจักรฮังกการี', "Newton's laws of motion": 'กฎการเคลื่อนที่ของนิวตัน', 'Pump': 'เครื่องสูบน้ำ', 'Reaction (physics)': 'แรงปฏิกิริยา (ฟิสิกส์)', 'Salmon': 'ปลาแซลมอน', 'Tuniisia': 'ประเทศตูนิเซีย'}

    test = translate_text(test_str)
    print(test)