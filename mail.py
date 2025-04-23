#!/usr/local/bin/python3
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timedelta
import os.path
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from bs4 import BeautifulSoup
import requests
import pandas as pd
import argparse
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
import logging
import sys

# 환경 확인 (서버인지 로컬인지)
IS_SERVER = os.path.exists('/home/hosting_users/ytonepd/www')

# GitHub Actions에서 실행할 때의 환경 설정
IS_GITHUB_ACTIONS = 'GITHUB_ACTIONS' in os.environ

# 로그 파일 경로 설정
if IS_SERVER:
    # 서버 환경
    log_file = '/home/hosting_users/ytonepd/www/mail.log'
    previous_data_file = '/home/hosting_users/ytonepd/www/previous_data.json'
    error_log_file = '/home/hosting_users/ytonepd/www/error_log.txt'
elif IS_GITHUB_ACTIONS:
    # GitHub Actions 환경
    log_file = os.path.join(os.getcwd(), 'mail.log')
    previous_data_file = os.path.join(os.getcwd(), 'previous_data.json')
    error_log_file = os.path.join(os.getcwd(), 'error_log.txt')
else:
    # 로컬 환경
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'mail.log')
    previous_data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'previous_data.json')
    error_log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'error_log.txt')

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def log_message(message):
    """로그 파일에 메시지 기록"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} - {message}"
    with open(log_file, 'a') as f:
        f.write(log_entry + "\n")
    print(log_entry)  # GitHub Actions 로그에 출력

def get_spreadsheet_data():
    """스프레드시트에서 데이터 가져오기"""
    log_message("스프레드시트 데이터 가져오기 시작")
    
    # JSON 파일 생성 (환경 변수에서 읽기)
    json_content = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    if not json_content:
        raise ValueError("환경 변수 'GOOGLE_SHEETS_CREDENTIALS'가 설정되지 않았습니다.")
    
    # 임시 JSON 파일 생성
    creds_file = 'service_account.json'
    with open(creds_file, 'w') as f:
        f.write(json_content)
    
    # 파일 생성 확인 로그
    if os.path.exists(creds_file):
        log_message(f"JSON 파일 생성 성공: {creds_file}")
    else:
        log_message(f"JSON 파일 생성 실패: {creds_file}")
        raise FileNotFoundError(f"JSON 파일을 생성할 수 없습니다: {creds_file}")
    
    # Google Sheets API 설정
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)

    # 스프레드시트 열기
    spreadsheet = client.open_by_key("1shWpyaGrQF00YKkmYGftL2IAEOgmZ8kjw2s-WKbdyGg")
    sheets = ["Naver_Ads", "Google_Ads", "Meta_Ads"]

    # 각 시트에서 가장 최근 작성일 데이터 추출
    latest_records = []
    for sheet_name in sheets:
        try:
            sheet = spreadsheet.worksheet(sheet_name)
            records = sheet.get_all_records()
            
            # 스프레드시트의 모든 행 가져오기 (최신 항목만이 아닌 전체 데이터)
            for record in records:
                record['sheet_name'] = sheet_name
                
                # 스프레드시트 열 이름 매핑
                # A1열: 제목 (title), B1열: 구분 (category), C1열: 작성일 (date)
                # D1열: 링크 (link), E1열: 내용 (content), F1열: 요약 (summary)
                # G1열: 30년차 (expert_advice), H1열: 본 공지의 중요성 (importance)
                # I1열: 실무 적용 제언 (actions)
                
                # 실제 스프레드시트 열 이름에 맞게 설정
                title_key = '제목'
                category_key = '구분'
                date_key = '작성일'  # C1열
                link_key = '링크'
                content_key = '내용'
                summary_key = '요약'
                expert_advice_key = '30년차'  # G1열
                importance_key = '본 공지의 중요성'  # H1열
                actions_key = '실무 적용 제언'  # I1열
                
                # 데이터 매핑
                record['title'] = record.get(title_key, '제목 없음')
                record['category'] = record.get(category_key, '')
                record['date'] = record.get(date_key, '')  # C1열 작성일
                record['original_link'] = record.get(link_key, '#')
                record['content'] = record.get(content_key, '')
                record['summary'] = record.get(summary_key, '요약 없음')
                record['expert_advice'] = record.get(expert_advice_key, '')  # G1열 30년차 조언
                record['importance'] = record.get(importance_key, '')  # H1열 본 공지의 중요성
                record['actions'] = record.get(actions_key, '')  # I1열 실무 적용 제언
                
                latest_records.append(record)
                
            log_message(f"{sheet_name} 시트에서 {len(records)}개의 데이터 가져옴")
            
        except Exception as e:
            log_message(f"{sheet_name} 시트 데이터 가져오기 실패: {str(e)}")

    log_message(f"총 {len(latest_records)}개의 데이터 가져옴")
    return latest_records

def send_email(subject, html_content, to_email):
    """이메일 전송"""
    log_message(f"이메일 전송 시작: {subject}")
    
    # SMTP 서버 설정
    smtp_server = 'smtp.naver.com'
    smtp_port = 465
    smtp_user = 'ytonemkt@naver.com'
    smtp_password = os.environ.get('EMAIL_PASSWORD', 'ytonecompany1!')

    # 이메일 구성
    msg = MIMEMultipart('alternative')
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    # 이메일 전송
    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(smtp_user, smtp_password)
        
        # 수신자가 쉼표로 구분된 문자열인 경우 리스트로 변환
        recipients = [email.strip() for email in to_email.split(',')] if isinstance(to_email, str) and ',' in to_email else [to_email]
        
        server.sendmail(smtp_user, recipients, msg.as_string())
        server.quit()
        log_message(f"이메일 전송 성공: {to_email}")
        return True
    except Exception as e:
        log_message(f"이메일 전송 실패: {e}")
        return False

def load_previous_data():
    """이전에 전송한 데이터 로드"""
    try:
        with open(previous_data_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        log_message("이전 데이터 파일이 없음, 새로 생성")
        return []
    except Exception as e:
        log_message(f"이전 데이터 로드 실패: {str(e)}")
        return []

def save_current_data(data):
    """현재 데이터 저장"""
    try:
        with open(previous_data_file, 'w') as file:
            json.dump(data, file)
        log_message("현재 데이터 저장 성공")
    except Exception as e:
        log_message(f"현재 데이터 저장 실패: {str(e)}")

def load_previous_data_from_sheet():
    """Google 스프레드시트에서 이전에 전송한 데이터 로드"""
    log_message("Google 스프레드시트에서 이전 데이터 로드 시작")
    
    try:
        # JSON 파일 생성 (환경 변수에서 읽기)
        json_content = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if not json_content:
            raise ValueError("환경 변수 'GOOGLE_SHEETS_CREDENTIALS'가 설정되지 않았습니다.")
        
        # 임시 JSON 파일 생성
        creds_file = 'service_account.json'
        with open(creds_file, 'w') as f:
            f.write(json_content)
        
        # Google Sheets API 설정
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
        client = gspread.authorize(creds)

        # 스프레드시트 열기
        spreadsheet = client.open_by_key("1shWpyaGrQF00YKkmYGftL2IAEOgmZ8kjw2s-WKbdyGg")
        
        # 이전 데이터 시트가 있는지 확인
        try:
            previous_data_sheet = spreadsheet.worksheet("PreviousData")
            records = previous_data_sheet.get_all_records()
            
            # 데이터 변환 (필요하다면)
            previous_data = []
            for record in records:
                # 스프레드시트에서는 행 단위로 데이터를 저장하므로
                # 각 행은 이전에 전송된 항목 하나를 나타냄
                previous_data.append({
                    "title": record.get("title", ""),
                    "sheet_name": record.get("sheet_name", "")
                })
            
            log_message(f"스프레드시트에서 {len(previous_data)}개의 이전 데이터 로드 성공")
            return previous_data
            
        except WorksheetNotFound:
            # 시트가 없으면 새로 생성
            log_message("PreviousData 시트가 없어 새로 생성합니다.")
            spreadsheet.add_worksheet(title="PreviousData", rows=1000, cols=10)
            # 헤더 설정
            previous_data_sheet = spreadsheet.worksheet("PreviousData")
            previous_data_sheet.append_row(["title", "sheet_name", "date_sent"])
            return []
            
    except Exception as e:
        log_message(f"스프레드시트에서 이전 데이터 로드 실패: {str(e)}")
        # 로컬 파일로 폴백
        return load_previous_data()

def save_current_data_to_sheet(data):
    """현재 데이터를 Google 스프레드시트에 저장"""
    log_message("현재 데이터를 Google 스프레드시트에 저장 시작")
    
    try:
        # JSON 파일 생성 (환경 변수에서 읽기)
        json_content = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if not json_content:
            raise ValueError("환경 변수 'GOOGLE_SHEETS_CREDENTIALS'가 설정되지 않았습니다.")
        
        # 임시 JSON 파일 생성
        creds_file = 'service_account.json'
        with open(creds_file, 'w') as f:
            f.write(json_content)
        
        # Google Sheets API 설정
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
        client = gspread.authorize(creds)

        # 스프레드시트 열기
        spreadsheet = client.open_by_key("1shWpyaGrQF00YKkmYGftL2IAEOgmZ8kjw2s-WKbdyGg")
        
        try:
            previous_data_sheet = spreadsheet.worksheet("PreviousData")
            
            # 기존 데이터를 딕셔너리로 변환하여 중복 제거
            existing_records = previous_data_sheet.get_all_records()
            unique_entries = {}
            
            # 기존 데이터에서 고유한 항목만 유지
            for record in existing_records:
                key = (record.get("title", ""), record.get("sheet_name", ""))
                if key not in unique_entries:
                    unique_entries[key] = record
            
            # 새 데이터 추가
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in data:
                key = (item.get("title", ""), item.get("sheet_name", ""))
                if key not in unique_entries:
                    unique_entries[key] = {
                        "title": item.get("title", ""),
                        "sheet_name": item.get("sheet_name", ""),
                        "date_sent": timestamp
                    }
            
            # 시트 초기화 및 헤더 추가
            previous_data_sheet.clear()
            previous_data_sheet.append_row(["title", "sheet_name", "date_sent"])
            
            # 고유한 데이터만 시트에 추가
            for entry in unique_entries.values():
                previous_data_sheet.append_row([
                    entry.get("title", ""),
                    entry.get("sheet_name", ""),
                    entry.get("date_sent", "")
                ])
            
            log_message(f"스프레드시트에 {len(unique_entries)} 개의 고유 데이터 저장 성공")
            
        except WorksheetNotFound:
            # 시트가 없으면 새로 생성
            log_message("PreviousData 시트가 없어 새로 생성합니다.")
            previous_data_sheet = spreadsheet.add_worksheet(title="PreviousData", rows=1000, cols=10)
            previous_data_sheet.append_row(["title", "sheet_name", "date_sent"])
            
            # 새 데이터 추가
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in data:
                previous_data_sheet.append_row([
                    item.get("title", ""),
                    item.get("sheet_name", ""),
                    timestamp
                ])
            
            log_message(f"새 시트에 {len(data)}개의 데이터 저장 성공")
            
    except Exception as e:
        log_message(f"스프레드시트에 데이터 저장 실패: {str(e)}")
        # 로컬 파일로 폴백
        save_current_data(data)

def parse_date(date_str):
    """다양한 날짜 형식을 파싱하는 함수"""
    try:
        # YYYY-MM-DD 형식
        if '-' in date_str:
            return datetime.strptime(date_str, "%Y-%m-%d")
        # YYYY/MM/DD 형식
        elif '/' in date_str:
            return datetime.strptime(date_str, "%Y/%m/%d")
        # YYYY년 MM월 DD일 형식
        elif '년' in date_str and '월' in date_str and '일' in date_str:
            date_str = date_str.replace('년 ', '-').replace('월 ', '-').replace('일', '')
            return datetime.strptime(date_str, "%Y-%m-%d")
        else:
            raise ValueError(f"지원하지 않는 날짜 형식: {date_str}")
    except Exception as e:
        log_message(f"날짜 파싱 오류 ({date_str}): {str(e)}")
        return None

def check_for_new_entries_and_notify():
    """새로운 항목 확인 및 이메일 전송"""
    log_message("새로운 항목 확인 시작")
    
    # 이전 데이터 로드 (Google 시트에서)
    previous_data = load_previous_data_from_sheet()

    # 현재 데이터 로드
    current_data = get_spreadsheet_data()
    
    # 기준 날짜를 어제로 설정
    reference_date = datetime.now() - timedelta(days=1)
    reference_date = reference_date.replace(hour=0, minute=0, second=0, microsecond=0)
    log_message(f"기준일자: {reference_date.strftime('%Y-%m-%d')}")

    # 새로운 데이터 감지 (제목과 시트 이름으로 비교 + 날짜 기준)
    new_entries = []
    for current_entry in current_data:
        date_str = current_entry.get('date', '')
        
        # 날짜 문자열 파싱
        try:
            if date_str:
                entry_date = parse_date(date_str)
                if not entry_date:
                    log_message(f"날짜 파싱 실패: {date_str}")
                    continue
                
                # 기준일자와 비교 (같은 날짜 포함)
                if entry_date.date() >= reference_date.date():
                    # 이전에 알림을 보낸 항목인지 확인
                    is_new = True
                    for prev_entry in previous_data:
                        if (current_entry.get('title') == prev_entry.get('title') and 
                            current_entry.get('sheet_name') == prev_entry.get('sheet_name')):
                            is_new = False
                            break
                    
                    if is_new:
                        new_entries.append(current_entry)
                        log_message(f"새 항목 감지: {current_entry.get('title')}, 작성일: {date_str}")
                else:
                    log_message(f"기준일자 이전 항목 건너뜀: {current_entry.get('title')}, 작성일: {date_str}")
                    continue

            else:
                log_message("작성일 데이터 없음")
                continue

        except Exception as e:
            log_message(f"날짜 처리 중 오류 발생: {str(e)}")
            continue

    log_message(f"새로운 항목 수: {len(new_entries)}")

    # 새로운 데이터가 있을 경우 이메일 전송
    if new_entries:
        for entry in new_entries:
            sheet_name = entry.get('sheet_name', 'Unknown')
            date_str = entry.get('date', '날짜 정보 없음')
            category = entry.get('category', '')
            title = entry.get('title', '제목 없음')
            summary = entry.get('summary', '요약 없음')
            content = entry.get('content', '')
            link = entry.get('original_link', '#')
            expert_advice = entry.get('expert_advice', '')  # G열 30년차 조언
            importance = entry.get('importance', '')  # H열 본 공지의 중요성
            actions = entry.get('actions', '')  # I열 실무 적용 제언
            
            # 제목 설정
            subject = f"[YTONE_Intelligence] {sheet_name} 신규 콘텐츠: {title}"
            
            # 콘텐츠 부분을 정리하고 불릿 포인트에 줄바꿈 적용
            content_formatted = ""
            if content:
                # 콘텐츠를 줄바꿈 기준으로 나누기
                paragraphs = content.split('\n')
                for paragraph in paragraphs:
                    paragraph = paragraph.strip()
                    if paragraph:
                        # '[주요 변경사항]', '[작품 예시]' 등의 섹션 제목은 그대로 유지
                        if paragraph.startswith('[') and paragraph.endswith(']'):
                            content_formatted += f"<p style='font-weight: bold; margin-top: 15px;'>{paragraph}</p>\n"
                        # 불릿 포인트(•)가 있는 경우 줄바꿈 처리
                        elif '•' in paragraph:
                            # 불릿 포인트를 기준으로 분리
                            parts = paragraph.split('•')
                            # 첫 부분은 보통 빈 문자열이거나 타이틀 등이 있을 수 있음
                            if parts[0].strip():
                                content_formatted += f"<p>{parts[0].strip()}</p>\n"
                            
                            # 각 불릿 포인트를 별도 라인으로 처리
                            for part in parts[1:]:
                                if part.strip():
                                    content_formatted += f"<p style='margin-left: 15px;'>• {part.strip()}</p>\n"
                        else:
                            content_formatted += f"<p>{paragraph}</p>\n"
            
            # 요약 부분도 불릿 포인트 처리
            summary_formatted = ""
            if summary:
                # 요약을 줄바꿈 기준으로 나누기
                summary_lines = summary.split('\n')
                for line in summary_lines:
                    line = line.strip()
                    if line:
                        # 불릿 포인트(•)가 있는 경우 줄바꿈 처리
                        if '•' in line:
                            # 불릿 포인트를 기준으로 분리
                            parts = line.split('•')
                            # 첫 부분은 보통 빈 문자열이거나 타이틀 등이 있을 수 있음
                            if parts[0].strip():
                                summary_formatted += f"<p>{parts[0].strip()}</p>\n"
                            
                            # 각 불릿 포인트를 별도 라인으로 처리
                            for part in parts[1:]:
                                if part.strip():
                                    summary_formatted += f"<p style='margin: 8px 0; margin-left: 15px;'>• {part.strip()}</p>\n"
                        else:
                            summary_formatted += f"<p>{line}</p>\n"
            
            # 추가: 30년차 조언, 본 공지의 중요성, 실무 적용 제언에 대한 포맷팅
            expert_advice_formatted = ""
            if expert_advice:
                expert_advice_lines = expert_advice.split('\n')
                for line in expert_advice_lines:
                    line = line.strip()
                    if line:
                        if '•' in line:
                            parts = line.split('•')
                            if parts[0].strip():
                                expert_advice_formatted += f"<p>{parts[0].strip()}</p>\n"
                            for part in parts[1:]:
                                if part.strip():
                                    expert_advice_formatted += f"<p style='margin: 8px 0; margin-left: 15px;'>• {part.strip()}</p>\n"
                        else:
                            expert_advice_formatted += f"<p>{line}</p>\n"
            
            importance_formatted = ""
            if importance:
                importance_lines = importance.split('\n')
                for line in importance_lines:
                    line = line.strip()
                    if line:
                        if '•' in line:
                            parts = line.split('•')
                            if parts[0].strip():
                                importance_formatted += f"<p>{parts[0].strip()}</p>\n"
                            for part in parts[1:]:
                                if part.strip():
                                    importance_formatted += f"<p style='margin: 8px 0; margin-left: 15px;'>• {part.strip()}</p>\n"
                        else:
                            importance_formatted += f"<p>{line}</p>\n"
            
            # 수정된 HTML 템플릿 - 최대 넓이 630px 및 중앙 정렬 추가
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{subject}</title>
            </head>
            <body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #333333; margin: 0; padding: 0; background-color: #f7f7f7;">
                <!-- 이메일 전체 컨테이너 - 최대 넓이 630px 및 중앙 정렬 -->
                <div style="max-width: 630px; margin: 0 auto; background-color: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    
                    <!-- 본문 내용 -->
                    <div style="padding: 20px;">
                        <div style="margin-bottom: 15px;">
                            <img src="https://ytonepd.mycafe24.com/img/mailtop.jpg" style="width: 100%">
                        </div>
                        
                        <h1 style="font-size: 22px; margin-bottom: 20px;">{sheet_name} 신규 콘텐츠 안내</h1>
                        
                        <p>안녕하세요. YTONE_Intelligence입니다.</p>
                        <p>최신 마케팅 콘텐츠를 받고 사용해주시는 와이토너님께 진심으로 감사드립니다.</p>
                        <p>{sheet_name}에서 새로운 콘텐츠가 등록되어 안내드립니다.</p>
                        
                        <div style="margin: 20px 0;">
                            <div style="font-weight: bold;">콘텐츠 제목</div>
                            <div style="margin-bottom: 10px;">{title}</div>
                            
                            <div style="font-weight: bold;">작성일</div>
                            <div style="margin-bottom: 10px;">{date_str}</div>
                            
                            <div style="font-weight: bold;">카테고리</div>
                            <div style="margin-bottom: 10px;">{category}</div>
                        </div>
                        
                        <!-- 콘텐츠 요약 - 불릿 포인트 개선 적용 -->
                        <div style="background-color: #f9f9f9; padding: 15px; margin: 15px 0; border-radius: 4px;">
                            <div style="font-weight: bold; margin-bottom: 10px;">AI가 요약한 내용</div>
                            <div style="line-height: 1.7;">
                                {summary_formatted if summary_formatted else summary}
                            </div>
                        </div>
                        
                        <!-- G열: 30년차 조언 -->
                        {f'''
                        <div style="background-color: #f3e5f5; padding: 15px; margin: 15px 0; border-radius: 4px; border-left: 3px solid #8e44ad;">
                            <div style="font-weight: bold; margin-bottom: 10px;">와이토너를 위한 제안</div>
                            <div style="line-height: 1.7;">
                                {expert_advice_formatted if expert_advice_formatted else expert_advice}
                            </div>
                        </div>
                        ''' if expert_advice else ''}
                        
                        <!-- H열: 본 공지의 중요성 -->
                        {f'''
                        <div style="background-color: #e3f2fd; padding: 15px; margin: 15px 0; border-radius: 4px; border-left: 3px solid #3498db;">
                            <div style="font-weight: bold; margin-bottom: 10px;">본 공지의 중요성</div>
                            <div style="line-height: 1.7;">
                                {importance_formatted if importance_formatted else importance}
                            </div>
                        </div>
                        ''' if importance else ''}
                        
                        <!-- 접근 방법 -->
                        <div style="margin-top: 20px; padding-top: 15px; border-top: 1px dashed #eeeeee;">
                            <div style="font-weight: bold; margin-bottom: 10px;">자세한 내용 살펴보기</div>
                            <div style="margin-bottom: 5px;"><a href="{link}" style="color: #0078ff;">여기</a>에서 원문 확인이 가능합니다.</div>
                            <div style="margin-bottom: 5px;">YTONE_Intelligence 홈페이지: <a href="https://ytoneintelligence.co.kr/" style="color: #0078ff;">https://ytoneintelligence.co.kr/</a>에서도 전체 콘텐츠를 확인하실 수 있습니다.</div>
                        </div>
                        
                        <p>앞으로도 YTONE_Intelligence는 와이토너님들께 더욱 다양한 정보를 제공하기 위해 노력하겠습니다. 감사합니다.</p>
                        
                        <!-- 푸터 -->
                        <div style="margin-top: 30px; padding-top: 15px; border-top: 1px solid #eeeeee; color: #666666; font-size: 12px;">
                            <div style="font-weight: bold; margin-bottom: 10px;">YTONE_Intelligence</div>
                            <div style="margin-bottom: 10px;"> 문의사항이 있으실 경우, <a href="mailto:th.yoon@y-tone.co.kr" style="color: #0078ff;">th.yoon@y-tone.co.kr</a>로 남겨주시기 바랍니다.</div>
                            <div>copyright © 와이톤 All rights reserved.</div>
                            <div>(주)와이톤 | 서울특별시 강남구 선릉로 131길 9, 하나빌딩 3층 & 10층</div>
                        </div>
                    </div>
                </div>
                
                <!-- 하단 여백 -->
                <div style="height: 20px;"></div>
            </body>
            </html>
            """
            
            # 이메일 전송
            success = send_email(subject, html_content, 'business@y-tone.co.kr, th.yoon@y-tone.co.kr, korea@y-tone.co.kr, design@y-tone.co.kr, production@y-tone.co.kr')
            if success:
                log_message(f"'{title}' 이메일 전송 성공")
            else:
                log_message(f"'{title}' 이메일 전송 실패")

    # 현재 데이터를 저장하여 다음 실행 시 비교
    save_current_data_to_sheet(current_data)
    
    log_message("새로운 항목 확인 완료")

def list_sheets():
    # Google Sheets API 설정
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('/Users/mmmo/Desktop/YOONKIJWALJWAL/Front/MaketingA/naver-452205-a733573ea425.json', scope)
    client = gspread.authorize(creds)

    # 스프레드시트 열기
    spreadsheet = client.open("마케팅 공지사항")

    # 모든 시트 이름 출력
    sheet_names = [sheet.title for sheet in spreadsheet.worksheets()]
    print("Available sheets:", sheet_names)

def reset_previous_data():
    """이전 데이터 기록을 초기화"""
    try:
        # 빈 리스트로 초기화
        with open(previous_data_file, 'w') as file:
            json.dump([], file)
        log_message("이전 데이터 기록 초기화 완료")
        return True
    except Exception as e:
        log_message(f"이전 데이터 초기화 실패: {str(e)}")
        return False

def setup_google_sheets():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    try:
        json_content = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if not json_content:
            raise ValueError("환경 변수 'GOOGLE_SHEETS_CREDENTIALS'가 설정되지 않았습니다.")
        
        creds_file = 'service_account.json'
        with open(creds_file, 'w') as f:
            f.write(json_content)

        if os.path.exists(creds_file):
            print(f"JSON 파일 생성 성공: {creds_file}")
        else:
            print(f"JSON 파일 생성 실패: {creds_file}")

        creds = service_account.Credentials.from_service_account_file(
            creds_file,
            scopes=scope
        )
        
        gc = gspread.authorize(creds)
        print("gspread 인증 성공")
        
        SPREADSHEET_ID = '1shWpyaGrQF00YKkmYGftL2IAEOgmZ8kjw2s-WKbdyGg'
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        print("스프레드시트 열기 성공")
        
        sheet = spreadsheet.worksheet('Boss_pdf')
        print("Boss_pdf 시트 열기 성공")
        
        return sheet
            
    except Exception as e:
        print(f"Google Sheets 설정 중 오류 발생: {str(e)}")
        raise

if __name__ == "__main__":
    log_message("메일 프로그램 시작")
    try:
        # 테스트 모드는 주석을 해제해서 활성화할 수 있습니다
        # reset_previous_data()
        # log_message("보낸 기록을 초기화하고 모든 항목을 새 항목으로 간주합니다.")
        
        # 정상 실행
        check_for_new_entries_and_notify()
        log_message("메일 프로그램 정상 종료")
    except Exception as e:
        error_msg = f"메일 프로그램 오류 발생: {str(e)}"
        log_message(error_msg)
        
        # 상세 오류 정보를 error_log 파일에 기록
        try:
            with open(error_log_file, 'a') as f:
                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n")
                f.write(error_msg + "\n")
                import traceback
                f.write(traceback.format_exc())
        except Exception as log_error:
            print(f"오류 로그 작성 실패: {str(log_error)}")
        
        # 프로그램 종료 코드 1로 설정하여 오류 상태 표시
        sys.exit(1)
