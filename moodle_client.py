import requests
from dotenv import load_dotenv
from typing import List, Dict, Tuple, Optional, Union
from datetime import datetime
import os

load_dotenv()

class MoodleClient:
    def __init__(self):
        self.url = os.getenv('MOODLE_URL')
        self.token = os.getenv('MOODLE_TOKEN')
        self.session = requests.Session()

    def call_api(self, function: str, **params) -> Optional[Dict]:
        """
        Получаем данные из API
        """
        params.update({
            'wstoken': self.token,
            'wsfunction': function,
            'moodlewsrestformat': 'json'
        })
        try:
            response = self.session.get(f"{self.url}/webservice/rest/server.php",
                                        params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API Error: {e}")
            return None

    def get_user_id_by_username(self, username: str) -> Optional[int]:
        """
        Получает ID пользователя по его имени (username).
        """
        try:
            criteria = [
                {
                    'key': 'email',
                    'value': username
                }
            ]

            params = {
                'criteria[0][key]': 'email',
                'criteria[0][value]': username
            }

            response = self.call_api('core_user_get_users', **params)

            if response['users']:
                user = response['users'][0]
                return user['id']
            else:
                print(f"Пользователь с именем {username} не найден.")
                return None

        except Exception as e:
            print(f"Ответ API: {response}")
            return None

    def get_teacher_courses(self, teacher_id: int, start_date: str, end_date: str) -> Optional[Tuple[List[Dict], int]]:
        """
        Получает список курсов преподавателя за указанный период
        """
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            if start_dt > end_dt:
                raise ValueError("Дата начала периода не может быть позже даты окончания")

            start_timestamp = int(start_dt.timestamp())
            end_timestamp = int(end_dt.timestamp())

            all_courses = self.call_api('core_enrol_get_users_courses', userid=teacher_id)
            if not isinstance(all_courses, list):
                return None

            filtered_courses = []
            for course in all_courses:
                if not all(key in course for key in ['id', 'fullname', 'startdate']):
                    continue

                course_start = course.get('startdate', 0)
                course_end = course.get('enddate', float('inf'))

                if (course_start >= start_timestamp and
                        (course_end <= end_timestamp or course_end == 0)):
                    filtered_courses.append({
                        'id': course['id'],
                        'fullname': course['fullname'],
                        'startdate': datetime.fromtimestamp(course_start).strftime('%Y-%m-%d'),
                        'enddate': datetime.fromtimestamp(course_end).strftime('%Y-%m-%d')
                        if course_end and course_end != float('inf')
                        else 'Не указана'
                    })

            return filtered_courses, len(filtered_courses)

        except ValueError as e:
            print(f"Ошибка формата даты: {e}")
            return None
        except Exception as e:
            print(f"Ошибка при получении курсов: {e}")
            return None

    def track_interim_assessment(self, course_id: int, start_date_str: str, end_date_str: str) -> Optional[Dict]:
        """
        Получение информации о промежуточной аттестации
        """
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

            grades_data = self.call_api('gradereport_user_get_grade_items', courseid=course_id)
            if not grades_data:
                print("API не вернуло данных")
                return None

            if 'usergrades' not in grades_data or not grades_data['usergrades']:
                print("Нет данных об оценках студентов")
                return None

            unique_items = {}
            for user in grades_data['usergrades']:
                for item in user.get('gradeitems', []):
                    item_id = item['id']
                    if item_id not in unique_items:
                        unique_items[item_id] = item

            interim_items = []
            for item_id, item in unique_items.items():
                try:
                    if not item.get('itemname'):
                        continue

                    item_info = {
                        'id': item_id,
                        'name': item.get('itemname', 'Без названия'),
                        'type': item.get('itemtype', 'unknown'),
                        'max_grade': item.get('grademax', 0)
                    }

                    if not item.get('gradedatesubmitted'):
                        item_info['date'] = 'Дата не указана'
                        interim_items.append(item_info)
                    else:
                        item_date = datetime.fromtimestamp(int(item['gradedatesubmitted']))
                        if start_date <= item_date <= end_date:
                            item_info['date'] = item_date.strftime('%Y-%m-%d')
                            interim_items.append(item_info)

                except Exception as e:
                    print(f"Ошибка обработки элемента оценки {item_id}: {e}")
                    continue

            if not interim_items:
                print("Нет подходящих элементов оценивания")
                return None

            students_grades = []
            for student in grades_data['usergrades']:
                try:
                    student_data = {
                        'userid': student['userid'],
                        'userfullname': student['userfullname'],
                        'grades': []
                    }

                    for item in interim_items:
                        for grade_item in student['gradeitems']:
                            if grade_item['id'] == item['id']:
                                student_data['grades'].append({
                                    'item': item['name'],
                                    'grade': grade_item.get('gradeformatted', '-'),
                                    'percentage': grade_item.get('percentageformatted', '-')
                                })
                                break

                    students_grades.append(student_data)
                except Exception as e:
                    print(f"Ошибка обработки студента {student.get('userid')}: {e}")
                    continue

            return {
                'course_id': course_id,
                'interim_items': interim_items,
                'students_grades': students_grades,
                'period': {
                    'start': start_date_str,
                    'end': end_date_str
                },
                'note': 'Элементы без даты включены в отчет'
            }

        except Exception as e:
            print(f"Ошибка при формировании отчета: {str(e)}")
            return None