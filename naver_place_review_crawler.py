from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
import time
import csv
import json
from datetime import datetime
import re

class NaverPlaceReviewCrawler:
    def __init__(self, headless=False):
        """네이버 플레이스 리뷰 크롤러 초기화"""
        self.setup_driver(headless)
        self.wait = WebDriverWait(self.driver, 15)
        self.all_reviews = []
        
    def setup_driver(self, headless):
        """크롬 드라이버 설정"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(f"webdriver-manager 실패, 기본 Chrome 시도: {e}")
            self.driver = webdriver.Chrome(options=chrome_options)
            
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def search_keyword(self, keyword):
        """네이버에서 키워드 검색 - 플레이스 검색 결과 페이지로 바로 이동"""
        print(f"'{keyword}' 검색 중...")
        import urllib.parse
        encoded = urllib.parse.quote(keyword)
        # 네이버 플레이스 검색 결과 페이지로 직접 이동
        self.driver.get(f"https://map.naver.com/v5/search/{encoded}")
        time.sleep(5)
        
    def wait_for_place_section(self):
        """플레이스 섹션이 로드될 때까지 대기"""
        try:
            # map.naver.com에서 searchIframe 로드 대기
            self.wait.until(
                EC.presence_of_element_located((By.ID, "searchIframe"))
            )
            time.sleep(3)
            print("플레이스 섹션 로드 완료")
            return True
        except TimeoutException:
            print("플레이스 섹션을 찾을 수 없습니다.")
            return None

    def click_place_more(self):
        """map.naver.com에서는 더보기 불필요 - 바로 리스트 표시됨"""
        print("map.naver.com 직접 접근 - 더보기 불필요")
        return True

    def switch_to_iframe(self):
        """searchIframe으로 전환"""
        try:
            print("iframe 전환 중...")
            self.driver.switch_to.default_content()
            iframe = self.wait.until(
                EC.presence_of_element_located((By.ID, "searchIframe"))
            )
            self.driver.switch_to.frame(iframe)
            time.sleep(3)
            print("iframe 전환 완료")
            return True
        except TimeoutException:
            print("searchIframe을 찾을 수 없습니다.")
            return False
            
    def get_place_list(self):
        """iframe 내부에서 업체 리스트 가져오기 (광고 제외)"""
        try:
            print("업체 리스트 로딩 대기 중...")
            # 리스트 컨테이너 대기 - 여러 셀렉터 시도
            list_selectors = ["ul", "#_pcmap_list_scroll_container"]
            for sel in list_selectors:
                try:
                    self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                    break
                except:
                    continue
            time.sleep(3)

            # 업체 li 항목 찾기 - 여러 셀렉터 시도
            all_places = []
            li_selectors = [
                "li[data-laim-exp-id]",
                "ul > li",
            ]
            for sel in li_selectors:
                all_places = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if all_places:
                    print(f"셀렉터 '{sel}'로 {len(all_places)}개 발견")
                    break

            print(f"전체 업체 요소 개수: {len(all_places)}")

            normal_places = []
            for i, place in enumerate(all_places):
                try:
                    # 광고 필터링: data-laim-exp-id 확인
                    exp_id = place.get_attribute("data-laim-exp-id") or ""
                    if exp_id == "undefined*e":
                        print(f"  -> 광고 제외 (index {i})")
                        continue

                    # 업체명: span.q2LdB (네이버 플레이스 업체명 클래스)
                    place_name = ""
                    name_elem = place.find_elements(By.CSS_SELECTOR, "span.q2LdB")
                    if name_elem:
                        place_name = name_elem[0].text.strip()

                    # 업체명을 못 찾으면 fallback
                    if not place_name:
                        spans = place.find_elements(By.CSS_SELECTOR, "span")
                        for span in spans:
                            sc = span.get_attribute("class") or ""
                            st = span.text.strip()
                            if st and len(st) > 2 and "이미지" not in st and "place_blind" not in sc:
                                place_name = st.split('\n')[0].strip()
                                break

                    if not place_name:
                        continue

                    # 클릭 요소: 업체명 텍스트가 포함된 a 태그
                    click_element = None
                    links = place.find_elements(By.CSS_SELECTOR, "a")
                    for link in links:
                        link_text = link.text.strip()
                        # 업체명이 포함된 링크를 찾기
                        if place_name[:4] in link_text:
                            click_element = link
                            break
                    # 못 찾으면 두번째 a 태그 (첫번째는 보통 이미지)
                    if not click_element and len(links) > 1:
                        click_element = links[1]
                    elif not click_element and links:
                        click_element = links[0]

                    if click_element and place_name:
                        normal_places.append({
                            'element': click_element,
                            'place_li': place,
                            'name': place_name,
                            'index': i
                        })
                        print(f"  -> 일반 업체로 추가: {place_name}")

                except Exception as e:
                    continue

            print(f"총 {len(normal_places)}개 일반 업체 발견 (광고 제외)")
            return normal_places[:20]

        except Exception as e:
            print(f"업체 리스트 가져오기 실패: {e}")
            return []

    def find_and_click_review_tab(self):
        """리뷰 탭 찾기 및 클릭"""
        print("리뷰 탭 찾는 중...")
        # 이 메서드는 extract_reviews_from_place에서 직접 처리하므로 여기서는 사용하지 않음
        return False

    def click_more_reviews_button(self):
        """리뷰 목록 하단의 '더보기' 버튼 클릭"""
        try:
            # 페이지 맨 아래로 스크롤하여 더보기 버튼 노출
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # 방법 1: "더보기" 텍스트가 포함된 모든 클릭 가능한 요소
            clickable = self.driver.find_elements(By.XPATH,
                "//a[contains(., '더보기')] | //button[contains(., '더보기')]")
            for elem in clickable:
                try:
                    elem_text = elem.text.strip()
                    # "리뷰 더보기" 또는 단순 "더보기"
                    if "더보기" in elem_text and len(elem_text) < 20:
                        print(f"    -> 리뷰 더보기 버튼 발견: '{elem_text}'")
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", elem)
                        time.sleep(3)
                        print(f"    -> 리뷰 더보기 버튼 클릭 성공!")
                        return True
                except:
                    continue

            # 방법 2: role="button" 속성을 가진 요소
            buttons = self.driver.find_elements(By.CSS_SELECTOR, '[role="button"]')
            for btn in buttons:
                try:
                    if "더보기" in btn.text:
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(3)
                        return True
                except:
                    continue

            print("    -> 리뷰 더보기 버튼을 찾을 수 없습니다.")
            return False

        except Exception as e:
            print(f"    -> 리뷰 더보기 버튼 클릭 중 오류: {e}")
            return False

    def extract_current_visible_reviews(self, seen_reviews):
        """현재 화면에 보이는 리뷰들 추출 (중복 제거)"""
        current_reviews = []

        try:
            # 리뷰 리스트 찾기 - 여러 셀렉터 시도
            review_items = []
            list_selectors = [
                ("#_review_list li", "id=_review_list"),
                ("ul li[class]", "ul > li"),
            ]
            for sel, desc in list_selectors:
                review_items = self.driver.find_elements(By.CSS_SELECTOR, sel)
                # 리뷰 항목은 보통 여러 개, 최소 1개 이상 텍스트가 있어야 함
                if len(review_items) >= 1:
                    print(f"    리뷰 리스트 발견 ({desc}): {len(review_items)}개")
                    break

            if not review_items:
                # XPath로 최후 시도 - 텍스트가 긴 요소들을 리뷰로 간주
                print("    CSS 셀렉터 실패, 텍스트 기반 추출 시도...")

            for item in review_items:
                try:
                    review_text = ""

                    # 1) 개별 리뷰 "더보기" 버튼 클릭 시도
                    more_btns = item.find_elements(By.XPATH,
                        ".//a[contains(text(),'접기') or contains(text(),'더보기')] | .//button[contains(text(),'더보기')]")
                    for btn in more_btns:
                        try:
                            if "더보기" in btn.text:
                                self.driver.execute_script("arguments[0].click();", btn)
                                time.sleep(0.5)
                        except:
                            pass

                    # 2) 리뷰 텍스트 추출 - data-pui-click-code 속성 활용
                    text_elems = item.find_elements(By.CSS_SELECTOR,
                        '[data-pui-click-code="rvshowless"], [data-pui-click-code="rvshowmore"]')
                    if text_elems:
                        review_text = text_elems[0].text.strip()

                    # 3) 위에서 못 찾으면 가장 긴 텍스트 블록 추출
                    if not review_text or len(review_text) <= 5:
                        # item 내 모든 텍스트 노드에서 가장 긴 것
                        all_texts = []
                        for child in item.find_elements(By.XPATH, ".//*"):
                            t = child.text.strip()
                            if t and len(t) > 10:
                                all_texts.append(t)
                        if all_texts:
                            review_text = max(all_texts, key=len)

                    # "더보기", "접기" 같은 버튼 텍스트 제거
                    if review_text:
                        review_text = review_text.replace("더보기", "").replace("접기", "").strip()

                    # 유효한 리뷰인지 확인 및 중복 방지
                    if (review_text and
                        len(review_text) > 5 and
                        review_text != "더보기" and
                        review_text not in seen_reviews):

                        seen_reviews.add(review_text)
                        current_reviews.append(review_text)
                        print(f"      새 리뷰 추가: {review_text[:50]}...")

                except Exception as item_error:
                    continue

        except Exception as list_error:
            print(f"    리뷰 리스트 찾기 실패: {list_error}")

        return current_reviews

    def extract_reviews_from_current_page(self, target_count=100):
        """현재 페이지에서 사용자 리뷰 추출 - 더보기 버튼 반복 클릭"""
        print(f"사용자 리뷰 추출 중... (목표: {target_count}개)")
        all_reviews = []
        seen_reviews = set()  # 중복 방지
        
        more_button_click_count = 0
        max_more_clicks = 30  # 더보기 버튼 최대 클릭 횟수 (100개 리뷰를 위해 증가)
        
        while len(all_reviews) < target_count and more_button_click_count < max_more_clicks:
            print(f"\n--- 더보기 클릭 {more_button_click_count + 1}/{max_more_clicks}, 현재 리뷰 수: {len(all_reviews)} ---")
            
            # 현재 페이지의 리뷰들 추출
            current_reviews = self.extract_current_visible_reviews(seen_reviews)
            
            if current_reviews:
                all_reviews.extend(current_reviews)
                print(f"  새로 추출된 리뷰: {len(current_reviews)}개")
                print(f"  총 리뷰 수: {len(all_reviews)}개")
                
                # 목표 달성 확인
                if len(all_reviews) >= target_count:
                    print(f"  목표 리뷰 수 달성! ({target_count}개)")
                    break
            else:
                print("  새로운 리뷰가 없습니다.")
            
            # 더보기 버튼 클릭 시도
            print(f"  더보기 버튼 클릭 시도...")
            more_clicked = self.click_more_reviews_button()
            
            if not more_clicked:
                print("  더보기 버튼을 찾을 수 없거나 클릭할 수 없습니다. 추출 종료.")
                break
                
            more_button_click_count += 1
            
            # 새 리뷰 로딩 대기
            time.sleep(3)
        
        final_reviews = all_reviews[:target_count]
        print(f"\n사용자 리뷰 추출 완료: {len(final_reviews)}개")
        return final_reviews

    def extract_reviews_from_place(self, place_name, target_count=100):
        """특정 업체에서 리뷰 추출"""
        print(f"\n=== {place_name}에서 리뷰 추출 시작 ===")

        try:
            time.sleep(3)

            # entryIframe으로 전환
            print("entryIframe으로 전환 중...")
            try:
                self.driver.switch_to.default_content()
                entry_iframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "entryIframe"))
                )
                self.driver.switch_to.frame(entry_iframe)
                time.sleep(3)
                print("entryIframe 전환 성공")
            except Exception as iframe_error:
                print(f"entryIframe 전환 실패: {iframe_error}")
                return []

            # 리뷰 탭 클릭 - 여러 방법 시도
            print("리뷰 탭 클릭 중...")
            review_tab_found = False

            # 방법 1: role="tab" 요소 중 "리뷰" 텍스트 포함된 것
            tabs = self.driver.find_elements(By.CSS_SELECTOR, '[role="tab"]')
            for tab in tabs:
                try:
                    if "리뷰" in tab.text:
                        self.driver.execute_script("arguments[0].click();", tab)
                        time.sleep(5)
                        print(f"리뷰 탭 클릭 성공: '{tab.text.strip()}'")
                        review_tab_found = True
                        break
                except:
                    continue

            # 방법 2: XPath로 "리뷰" 텍스트를 가진 a/button 찾기
            if not review_tab_found:
                xpath_selectors = [
                    "//a[contains(., '리뷰')]",
                    "//button[contains(., '리뷰')]",
                    "//span[contains(text(), '리뷰')]/ancestor::a",
                    "//span[contains(text(), '리뷰')]/ancestor::button",
                ]
                for xpath in xpath_selectors:
                    try:
                        elems = self.driver.find_elements(By.XPATH, xpath)
                        for elem in elems:
                            elem_text = elem.text.strip()
                            if "리뷰" in elem_text and len(elem_text) < 30:
                                self.driver.execute_script("arguments[0].click();", elem)
                                time.sleep(5)
                                print(f"리뷰 탭 클릭 성공 (XPath): '{elem_text}'")
                                review_tab_found = True
                                break
                    except:
                        continue
                    if review_tab_found:
                        break

            if not review_tab_found:
                print("모든 리뷰 탭 클릭 방법 실패")
                return []

            # 리뷰 추출
            reviews = self.extract_reviews_from_current_page(target_count)
            return reviews

        except Exception as e:
            print(f"리뷰 추출 중 오류: {e}")
            return []

    def get_place_name(self, place_dict):
        """업체명 추출"""
        try:
            if 'name' in place_dict and place_dict['name']:
                return place_dict['name']
            return f"업체_{place_dict.get('index', 0)}"
        except Exception as e:
            print(f"업체명 추출 실패: {e}")
            return f"업체명_추출_실패_{place_dict.get('index', 0)}"

    def crawl_reviews(self, keyword, max_places=20, reviews_per_place=100):
        """전체 크롤링 프로세스"""
        print(f"=== {keyword} 리뷰 크롤링 시작 ===")
        
        # 1. 키워드 검색
        self.search_keyword(keyword)
        
        # 2. 플레이스 섹션 대기
        place_section = self.wait_for_place_section()
        if not place_section:
            return False
            
        # 3. 플레이스 섹션 내의 더보기 (map.naver.com에서는 불필요)
        self.click_place_more()

        # 4. iframe으로 전환
        if not self.switch_to_iframe():
            return False
        
        # 5. 업체 리스트 가져오기
        places = self.get_place_list()
        if not places:
            print("업체 리스트를 가져올 수 없습니다.")
            return False
            
        # 6. 각 업체별 리뷰 추출
        for i, place_dict in enumerate(places[:max_places], 1):
            try:
                place_name = self.get_place_name(place_dict)
                print(f"\n[{i}/{max_places}] {place_name} 처리 중...")
                
                # 업체 클릭
                click_element = place_dict['element']
                self.driver.execute_script("arguments[0].scrollIntoView(true);", click_element)
                time.sleep(1)
                
                # 클릭 시도
                click_success = False
                click_methods = [
                    lambda: click_element.click(),
                    lambda: self.driver.execute_script("arguments[0].click();", click_element),
                    lambda: self.driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));", click_element)
                ]
                
                for method_idx, click_method in enumerate(click_methods):
                    try:
                        print(f"  클릭 방법 {method_idx + 1} 시도...")
                        click_method()
                        time.sleep(3)
                        click_success = True
                        print(f"  클릭 성공!")
                        break
                    except Exception as click_error:
                        print(f"  클릭 방법 {method_idx + 1} 실패: {click_error}")
                        continue
                
                if not click_success:
                    print(f"  모든 클릭 방법 실패, 다음 업체로...")
                    continue

                # map.naver.com에서는 클릭 시 entryIframe이 갱신됨 (새 창 X)
                time.sleep(3)
                
                # 리뷰 추출 (더보기 버튼 자동 클릭 포함)
                reviews = self.extract_reviews_from_place(place_name, reviews_per_place)
                
                # 결과 저장
                place_data = {
                    'keyword': keyword,
                    'rank': i,
                    'place_name': place_name,
                    'reviews': reviews,
                    'review_count': len(reviews),
                    'crawled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                self.all_reviews.append(place_data)
                
                # *** 리뷰 추출 후 searchIframe으로 복귀 ***
                print(f"  리뷰 추출 완료, 업체 목록으로 돌아가는 중...")

                try:
                    # default_content로 돌아간 후 searchIframe으로 전환
                    self.driver.switch_to.default_content()
                    time.sleep(1)

                    # searchIframe으로 다시 전환
                    search_iframe = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, "searchIframe"))
                    )
                    self.driver.switch_to.frame(search_iframe)
                    time.sleep(2)
                    print("  searchIframe 복귀 성공")
                except Exception as nav_error:
                    print(f"  searchIframe 복귀 실패: {nav_error}")
                    # 최후 수단: 뒤로가기
                    try:
                        self.driver.switch_to.default_content()
                        self.driver.back()
                        time.sleep(3)
                        self.switch_to_iframe()
                    except:
                        pass
                
            except Exception as e:
                print(f"업체 {i} 처리 실패: {e}")
                # 에러 발생시 searchIframe 복귀 시도
                try:
                    self.driver.switch_to.default_content()
                    self.switch_to_iframe()
                    time.sleep(2)
                except:
                    pass
                continue
                
        print(f"\n=== 크롤링 완료: 총 {len(self.all_reviews)}개 업체 ===")
        return True

    def save_individual_files(self):
        """업체별로 개별 파일 저장"""
        print("\n[파일] 업체별 개별 파일 저장 중...")
        
        for place_data in self.all_reviews:
            # 업체명에서 파일명 금지 문자 제거
            safe_place_name = re.sub(r'[<>:"/\\|?*]', '', place_data['place_name'])
            safe_keyword = re.sub(r'[<>:"/\\|?*]', '', place_data['keyword'])
            
            # CSV 파일 저장
            csv_filename = f"{safe_keyword}_{safe_place_name}.csv"
            with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['키워드', '순위', '업체명', '리뷰번호', '리뷰내용', '크롤링시간'])
                
                for i, review in enumerate(place_data['reviews'], 1):
                    writer.writerow([
                        place_data['keyword'],
                        place_data['rank'],
                        place_data['place_name'],
                        i,
                        review,
                        place_data['crawled_at']
                    ])
            
            # 텍스트 파일 저장
            txt_filename = f"{safe_keyword}_{safe_place_name}.txt"
            with open(txt_filename, 'w', encoding='utf-8') as f:
                # 개별 업체 헤더
                f.write("=" * 60 + "\n")
                f.write(f"[업체] {place_data['place_name']} 리뷰 분석\n")
                f.write(f"키워드: {place_data['keyword']}\n")
                f.write(f"순위: {place_data['rank']}위\n")
                f.write(f"리뷰 수: {len(place_data['reviews'])}개\n")
                f.write(f"수집 시간: {place_data['crawled_at']}\n")
                f.write("=" * 60 + "\n\n")
                
                # 리뷰 내용
                for i, review in enumerate(place_data['reviews'], 1):
                    f.write(f"리뷰 {i}: {review}\n\n")
            
            print(f"  [완료] {safe_place_name} 파일 저장 완료")
        
        print(f"[파일] 총 {len(self.all_reviews)}개 업체의 개별 파일 저장 완료!")

    def save_to_csv(self, filename=None):
        """전체 통합 CSV 파일로 저장"""
        if not filename:
            # 키워드를 그대로 파일명으로 사용 (특수문자만 제거)
            safe_keyword = re.sub(r'[<>:"/\\|?*]', '', self.all_reviews[0]['keyword']) if self.all_reviews else "default"
            filename = f"{safe_keyword}_전체.csv"
            
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['키워드', '순위', '업체명', '리뷰번호', '리뷰내용', '크롤링시간'])
            
            for place_data in self.all_reviews:
                for i, review in enumerate(place_data['reviews'], 1):
                    writer.writerow([
                        place_data['keyword'],
                        place_data['rank'],
                        place_data['place_name'],
                        i,
                        review,
                        place_data['crawled_at']
                    ])
                    
        print(f"CSV 통합 파일 저장 완료: {filename}")
        
    def save_to_json(self, filename=None):
        """전체 통합 JSON 파일로 저장"""
        if not filename:
            # 키워드를 그대로 파일명으로 사용 (특수문자만 제거)
            safe_keyword = re.sub(r'[<>:"/\\|?*]', '', self.all_reviews[0]['keyword']) if self.all_reviews else "default"
            filename = f"{safe_keyword}_전체.json"
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.all_reviews, f, ensure_ascii=False, indent=2)
            
        print(f"JSON 통합 파일 저장 완료: {filename}")
    
    def save_to_text(self, filename=None):
        """전체 통합 텍스트 파일로 저장 - 요청한 형식"""
        if not filename:
            # 키워드를 그대로 파일명으로 사용 (특수문자만 제거)
            safe_keyword = re.sub(r'[<>:"/\\|?*]', '', self.all_reviews[0]['keyword']) if self.all_reviews else "default"
            filename = f"{safe_keyword}_전체.txt"
            
        with open(filename, 'w', encoding='utf-8') as f:
            # 헤더 정보
            f.write("=" * 60 + "\n")
            f.write(f"네이버 플레이스 리뷰 분석 결과\n")
            f.write(f"키워드: {self.all_reviews[0]['keyword'] if self.all_reviews else 'N/A'}\n")
            f.write(f"수집 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"총 업체 수: {len(self.all_reviews)}개\n")
            total_reviews = sum(len(place['reviews']) for place in self.all_reviews)
            f.write(f"총 리뷰 수: {total_reviews}개\n")
            f.write("=" * 60 + "\n\n")
            
            # 각 업체별 리뷰 저장
            for place_data in self.all_reviews:
                f.write(f"[업체] {place_data['place_name']}\n")
                f.write(f"   순위: {place_data['rank']}위\n")
                f.write(f"   리뷰 수: {len(place_data['reviews'])}개\n")
                f.write(f"   수집 시간: {place_data['crawled_at']}\n")
                f.write("-" * 50 + "\n")
                
                # 리뷰 내용
                for i, review in enumerate(place_data['reviews'], 1):
                    f.write(f"리뷰 {i}: {review}\n\n")
                
                f.write("\n" + "=" * 60 + "\n\n")
                    
        print(f"텍스트 통합 파일 저장 완료: {filename}")
        
    def close(self):
        """브라우저 종료"""
        self.driver.quit()

# 사용 예시
def main():
    keyword = input("검색할 키워드를 입력하세요: ")
    
    crawler = NaverPlaceReviewCrawler(headless=False)
    
    try:
        success = crawler.crawl_reviews(
            keyword=keyword,
            max_places=5,        # 테스트를 위해 5개로 줄임
            reviews_per_place=100 # 업체당 100개 리뷰로 변경
        )
        
        if success and crawler.all_reviews:
            print("\n" + "=" * 50)
            print("[저장] 파일 저장 옵션")
            print("=" * 50)
            print("1. 전체 통합 파일 (모든 업체 리뷰를 하나의 파일에)")
            print("2. 업체별 개별 파일 (각 업체마다 별도 파일)")
            print("3. 둘 다 저장")
            
            choice = input("\n선택하세요 (1/2/3): ").strip()
            
            if choice in ['1', '3']:
                # 전체 통합 파일 저장
                crawler.save_to_csv()      # 통합 CSV
                crawler.save_to_json()     # 통합 JSON  
                crawler.save_to_text()     # 통합 텍스트
                
            if choice in ['2', '3']:
                # 업체별 개별 파일 저장
                crawler.save_individual_files()
            
            total_reviews = sum(len(place['reviews']) for place in crawler.all_reviews)
            print(f"\n=== 최종 결과 ===")
            print(f"처리된 업체 수: {len(crawler.all_reviews)}")
            print(f"총 리뷰 수: {total_reviews}")
            
            for place in crawler.all_reviews:
                print(f"- {place['place_name']}: {place['review_count']}개 리뷰")
                
        else:
            print("크롤링 결과가 없습니다.")
            
    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")
        
    finally:
        crawler.close()

if __name__ == "__main__":
    main()