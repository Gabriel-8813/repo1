import requests
import sys
import json
from datetime import datetime

class MediTransAPITester:
    def __init__(self, base_url="https://healthcargo-on.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"    Details: {details}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if headers:
            test_headers.update(headers)
        
        if self.token and 'Authorization' not in test_headers:
            test_headers['Authorization'] = f'Bearer {self.token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=10)

            success = response.status_code == expected_status
            
            if success:
                try:
                    response_data = response.json()
                    self.log_test(name, True, f"Status: {response.status_code}")
                    return True, response_data
                except:
                    self.log_test(name, True, f"Status: {response.status_code} (No JSON response)")
                    return True, {}
            else:
                try:
                    error_data = response.json()
                    self.log_test(name, False, f"Expected {expected_status}, got {response.status_code}: {error_data}")
                except:
                    self.log_test(name, False, f"Expected {expected_status}, got {response.status_code}")
                return False, {}

        except Exception as e:
            self.log_test(name, False, f"Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test API health check"""
        return self.run_test("Health Check", "GET", "", 200)

    def test_user_registration(self):
        """Test user registration"""
        timestamp = datetime.now().strftime('%H%M%S')
        user_data = {
            "email": f"test_driver_{timestamp}@meditrans.ca",
            "password": "TestPass123!",
            "full_name": "Test Driver",
            "phone": "+1-416-555-0123"
        }
        
        success, response = self.run_test(
            "User Registration", 
            "POST", 
            "auth/register", 
            200, 
            user_data
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.user_id = response['user']['id']
            return True
        return False

    def test_user_login(self):
        """Test user login with existing credentials"""
        if not self.token or not hasattr(self, 'test_email'):
            return False
            
        # Use the same email from registration
        login_data = {
            "email": self.test_email,
            "password": "TestPass123!"
        }
        
        success, response = self.run_test(
            "User Login", 
            "POST", 
            "auth/login", 
            200, 
            login_data
        )
        
        return success and 'access_token' in response

    def test_get_current_user(self):
        """Test getting current user info"""
        if not self.token:
            return False
            
        success, response = self.run_test(
            "Get Current User", 
            "GET", 
            "auth/me", 
            200
        )
        
        return success and 'id' in response

    def test_get_subscription_plans(self):
        """Test getting subscription plans"""
        success, response = self.run_test(
            "Get Subscription Plans", 
            "GET", 
            "subscriptions/plans", 
            200
        )
        
        if success and 'plans' in response:
            plans = response['plans']
            expected_plans = ['basic', 'pro', 'premium']
            has_all_plans = all(plan in plans for plan in expected_plans)
            
            if has_all_plans:
                # Check plan details
                basic_plan = plans.get('basic', {})
                if basic_plan.get('price') == 49.0:
                    self.log_test("Subscription Plans Validation", True, "All plans present with correct pricing")
                    return True
                else:
                    self.log_test("Subscription Plans Validation", False, f"Basic plan price incorrect: {basic_plan.get('price')}")
            else:
                self.log_test("Subscription Plans Validation", False, f"Missing plans. Found: {list(plans.keys())}")
        
        return False

    def test_get_permits(self):
        """Test getting Ontario permits"""
        success, response = self.run_test(
            "Get Ontario Permits", 
            "GET", 
            "permits", 
            200
        )
        
        if success and 'permits' in response:
            permits = response['permits']
            required_permits = [p for p in permits if p.get('required', False)]
            
            if len(required_permits) >= 4:  # Should have at least 4 required permits
                self.log_test("Permits Validation", True, f"Found {len(required_permits)} required permits")
                return True
            else:
                self.log_test("Permits Validation", False, f"Only {len(required_permits)} required permits found")
        
        return False

    def test_driver_permits(self):
        """Test driver permit management"""
        if not self.token:
            return False
            
        # Get driver permits
        success, response = self.run_test(
            "Get Driver Permits", 
            "GET", 
            "driver/permits", 
            200
        )
        
        if not success:
            return False
            
        # Update a permit status
        success, response = self.run_test(
            "Update Driver Permit", 
            "PUT", 
            "driver/permits/cvor?completed=true", 
            200
        )
        
        return success

    def test_fee_agreement(self):
        """Test fee agreement endpoint"""
        success, response = self.run_test(
            "Get Fee Agreement", 
            "GET", 
            "fees/agreement", 
            200
        )
        
        if success and 'agreement' in response:
            agreement = response['agreement']
            required_fields = ['base_rate_per_km', 'minimum_fee', 'platform_commission']
            
            if all(field in agreement for field in required_fields):
                self.log_test("Fee Agreement Validation", True, "All required fields present")
                return True
            else:
                missing = [f for f in required_fields if f not in agreement]
                self.log_test("Fee Agreement Validation", False, f"Missing fields: {missing}")
        
        return False

    def test_jobs_endpoints(self):
        """Test job-related endpoints"""
        if not self.token:
            return False
            
        # Get available jobs
        success1, response1 = self.run_test(
            "Get Available Jobs", 
            "GET", 
            "jobs/available", 
            200
        )
        
        # Get my jobs
        success2, response2 = self.run_test(
            "Get My Jobs", 
            "GET", 
            "jobs/my", 
            200
        )
        
        # Get all jobs
        success3, response3 = self.run_test(
            "Get All Jobs", 
            "GET", 
            "jobs", 
            200
        )
        
        return success1 and success2 and success3

    def test_earnings_endpoints(self):
        """Test earnings endpoints"""
        if not self.token:
            return False
            
        # Get earnings stats
        success1, response1 = self.run_test(
            "Get Earnings Stats", 
            "GET", 
            "earnings/stats", 
            200
        )
        
        # Get earnings history
        success2, response2 = self.run_test(
            "Get Earnings History", 
            "GET", 
            "earnings", 
            200
        )
        
        if success1 and 'total_earnings' in response1:
            self.log_test("Earnings Stats Validation", True, "Stats structure correct")
            return success1 and success2
        
        return False

    def test_payment_history(self):
        """Test payment history endpoint"""
        if not self.token:
            return False
            
        success, response = self.run_test(
            "Get Payment History", 
            "GET", 
            "payments/history", 
            200
        )
        
        return success and 'transactions' in response

    def test_stripe_checkout_creation(self):
        """Test Stripe checkout session creation"""
        if not self.token:
            return False
            
        checkout_data = {
            "plan_id": "basic",
            "origin_url": "https://healthcargo-on.preview.emergentagent.com"
        }
        
        success, response = self.run_test(
            "Create Stripe Checkout", 
            "POST", 
            "payments/checkout", 
            200, 
            checkout_data
        )
        
        if success and 'checkout_url' in response and 'session_id' in response:
            self.log_test("Stripe Checkout Validation", True, "Checkout URL and session ID returned")
            return True
        
        return False

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting MediTrans Ontario API Tests")
        print("=" * 50)
        
        # Test sequence
        tests = [
            self.test_health_check,
            self.test_user_registration,
            self.test_user_login,
            self.test_get_current_user,
            self.test_get_subscription_plans,
            self.test_get_permits,
            self.test_driver_permits,
            self.test_fee_agreement,
            self.test_jobs_endpoints,
            self.test_earnings_endpoints,
            self.test_payment_history,
            self.test_stripe_checkout_creation
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                self.log_test(f"Test {test.__name__}", False, f"Exception: {str(e)}")
        
        # Print summary
        print("\n" + "=" * 50)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print("❌ Some tests failed. Check details above.")
            return 1

def main():
    tester = MediTransAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())