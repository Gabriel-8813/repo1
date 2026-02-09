import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { 
  Truck, CreditCard, CheckCircle, Clock, DollarSign, 
  FileText, LogOut, ArrowRight, Calendar
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BillingPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, token, logout, refreshUser } = useAuth();
  const [plans, setPlans] = useState({});
  const [feeAgreement, setFeeAgreement] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processingPlan, setProcessingPlan] = useState(null);
  const [checkingPayment, setCheckingPayment] = useState(false);

  useEffect(() => {
    fetchData();
    checkPaymentStatus();
  }, [token]);

  const fetchData = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [plansRes, feeRes, transactionsRes] = await Promise.all([
        axios.get(`${API}/subscriptions/plans`, { headers }),
        axios.get(`${API}/fees/agreement`, { headers }),
        axios.get(`${API}/payments/history`, { headers })
      ]);
      setPlans(plansRes.data.plans);
      setFeeAgreement(feeRes.data.agreement);
      setTransactions(transactionsRes.data.transactions);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  const checkPaymentStatus = async () => {
    const sessionId = searchParams.get('session_id');
    if (!sessionId) return;

    setCheckingPayment(true);
    let attempts = 0;
    const maxAttempts = 5;

    const poll = async () => {
      try {
        const response = await axios.get(`${API}/payments/status/${sessionId}`, {
          headers: { Authorization: `Bearer ${token}` }
        });

        if (response.data.payment_status === 'paid') {
          toast.success('Payment successful! Your subscription is now active.');
          await refreshUser();
          fetchData();
          // Clear the session_id from URL
          navigate('/billing', { replace: true });
          setCheckingPayment(false);
          return;
        }

        if (response.data.status === 'expired') {
          toast.error('Payment session expired. Please try again.');
          navigate('/billing', { replace: true });
          setCheckingPayment(false);
          return;
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 2000);
        } else {
          toast.info('Payment is being processed. Please check back in a moment.');
          setCheckingPayment(false);
        }
      } catch (error) {
        console.error('Error checking payment status:', error);
        setCheckingPayment(false);
      }
    };

    poll();
  };

  const handleSubscribe = async (planId) => {
    setProcessingPlan(planId);
    try {
      const response = await axios.post(
        `${API}/payments/checkout`,
        { plan_id: planId, origin_url: window.location.origin },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      // Redirect to Stripe checkout
      window.location.href = response.data.checkout_url;
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to start checkout');
      setProcessingPlan(null);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const formatDate = (isoString) => {
    return new Date(isoString).toLocaleDateString('en-CA', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const planOrder = ['basic', 'pro', 'premium'];

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Navigation */}
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <Link to="/dashboard" className="flex items-center gap-2">
                <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                  <Truck className="w-6 h-6 text-white" />
                </div>
                <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
              </Link>
              <div className="hidden md:flex items-center gap-1">
                <Link to="/dashboard" className="nav-link">Dashboard</Link>
                <Link to="/jobs" className="nav-link">Jobs</Link>
                <Link to="/permits" className="nav-link">Permits</Link>
                <Link to="/billing" className="nav-link active">Billing</Link>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
              <LogOut className="w-4 h-4 mr-2" /> Logout
            </Button>
          </div>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="font-archivo font-bold text-3xl text-slate-900">Billing & Subscription</h1>
          <p className="text-slate-600 mt-1">Manage your subscription and view payment history</p>
        </div>

        {/* Payment Processing Banner */}
        {checkingPayment && (
          <Card className="mb-8 border-blue-200 bg-blue-50">
            <CardContent className="p-6">
              <div className="flex items-center gap-4">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <div>
                  <h3 className="font-semibold text-blue-900">Processing Payment</h3>
                  <p className="text-blue-700 text-sm">Please wait while we verify your payment...</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Current Subscription */}
        {user?.subscription_plan && (
          <Card className="mb-8 border-2 border-emerald-200 bg-emerald-50">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 bg-emerald-100 rounded-xl flex items-center justify-center">
                    <CheckCircle className="w-8 h-8 text-emerald-600" />
                  </div>
                  <div>
                    <h2 className="font-archivo font-bold text-xl text-slate-900">
                      {plans[user.subscription_plan]?.name || user.subscription_plan} Plan Active
                    </h2>
                    <p className="text-slate-600 text-sm">
                      Expires: {user.subscription_expires ? formatDate(user.subscription_expires) : 'N/A'}
                    </p>
                  </div>
                </div>
                <Badge className="bg-emerald-100 text-emerald-700 text-lg px-4 py-2">
                  ${plans[user.subscription_plan]?.price}/mo
                </Badge>
              </div>
            </CardContent>
          </Card>
        )}

        <Tabs defaultValue="plans">
          <TabsList className="mb-6">
            <TabsTrigger value="plans" data-testid="plans-tab">Subscription Plans</TabsTrigger>
            <TabsTrigger value="fees" data-testid="fees-tab">Fee Agreement</TabsTrigger>
            <TabsTrigger value="history" data-testid="history-tab">Payment History</TabsTrigger>
          </TabsList>

          {/* Subscription Plans */}
          <TabsContent value="plans">
            <div className="grid md:grid-cols-3 gap-6">
              {planOrder.map((planId, index) => {
                const plan = plans[planId];
                if (!plan) return null;
                const isCurrent = user?.subscription_plan === planId;
                const isHighlighted = planId === 'pro';
                
                return (
                  <Card 
                    key={planId}
                    className={`relative border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] ${
                      isHighlighted ? 'border-2 border-blue-600 shadow-[0_8px_24px_rgba(37,99,235,0.15)]' : ''
                    } ${isCurrent ? 'bg-emerald-50' : ''}`}
                  >
                    {isHighlighted && (
                      <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs font-semibold px-3 py-1 rounded-full">
                        Most Popular
                      </div>
                    )}
                    <CardContent className="p-8">
                      <div className="text-center mb-6">
                        <h3 className="font-archivo font-bold text-xl text-slate-900 mb-2">{plan.name}</h3>
                        <div className="flex items-baseline justify-center gap-1">
                          <span className="font-archivo font-black text-5xl text-slate-900">${plan.price}</span>
                          <span className="text-slate-500">/mo</span>
                        </div>
                        <p className="text-xs text-slate-400 mt-1">CAD • Billed monthly</p>
                      </div>
                      
                      <ul className="space-y-3 mb-8">
                        {plan.features.map((feature, i) => (
                          <li key={i} className="flex items-center gap-2 text-slate-600">
                            <CheckCircle className="w-5 h-5 text-emerald-500 flex-shrink-0" />
                            <span className="text-sm">{feature}</span>
                          </li>
                        ))}
                      </ul>

                      {isCurrent ? (
                        <Button className="w-full rounded-full" variant="outline" disabled>
                          <CheckCircle className="w-4 h-4 mr-2" />
                          Current Plan
                        </Button>
                      ) : (
                        <Button
                          className={`w-full rounded-full ${
                            isHighlighted ? 'bg-blue-600 hover:bg-blue-700' : 'bg-slate-900 hover:bg-slate-800'
                          }`}
                          onClick={() => handleSubscribe(planId)}
                          disabled={processingPlan === planId}
                          data-testid={`subscribe-${planId}-btn`}
                        >
                          {processingPlan === planId ? (
                            <>
                              <Clock className="w-4 h-4 mr-2 animate-spin" />
                              Processing...
                            </>
                          ) : (
                            <>
                              Subscribe <ArrowRight className="w-4 h-4 ml-2" />
                            </>
                          )}
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>

          {/* Fee Agreement */}
          <TabsContent value="fees">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader>
                <CardTitle className="font-archivo text-xl">Driver Fee Agreement</CardTitle>
                <p className="text-slate-600 text-sm">
                  Standard rates for medical transport jobs in Ontario
                </p>
              </CardHeader>
              <CardContent>
                {feeAgreement && (
                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="space-y-4">
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Base Rate per Kilometer</p>
                        <p className="font-archivo font-bold text-2xl text-slate-900">
                          ${feeAgreement.base_rate_per_km.toFixed(2)} CAD/km
                        </p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Minimum Fee per Job</p>
                        <p className="font-archivo font-bold text-2xl text-slate-900">
                          ${feeAgreement.minimum_fee.toFixed(2)} CAD
                        </p>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-lg">
                        <p className="text-sm text-slate-500 mb-1">Temperature Controlled Fee</p>
                        <p className="font-archivo font-bold text-2xl text-slate-900">
                          +${feeAgreement.temperature_controlled_fee.toFixed(2)} CAD
                        </p>
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="p-4 bg-amber-50 rounded-lg border border-amber-200">
                        <p className="text-sm text-amber-700 mb-1">Urgent Delivery Multiplier</p>
                        <p className="font-archivo font-bold text-2xl text-amber-800">
                          {feeAgreement.urgent_multiplier}x Base Rate
                        </p>
                      </div>
                      <div className="p-4 bg-red-50 rounded-lg border border-red-200">
                        <p className="text-sm text-red-700 mb-1">Emergency Delivery Multiplier</p>
                        <p className="font-archivo font-bold text-2xl text-red-800">
                          {feeAgreement.emergency_multiplier}x Base Rate
                        </p>
                      </div>
                      <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                        <p className="text-sm text-blue-700 mb-1">Platform Commission</p>
                        <p className="font-archivo font-bold text-2xl text-blue-800">
                          {(feeAgreement.platform_commission * 100).toFixed(0)}%
                        </p>
                        <p className="text-xs text-blue-600 mt-1">Deducted from job earnings</p>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Payment History */}
          <TabsContent value="history">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader>
                <CardTitle className="font-archivo text-xl">Payment History</CardTitle>
              </CardHeader>
              <CardContent>
                {transactions.length === 0 ? (
                  <div className="text-center py-12">
                    <CreditCard className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                    <h3 className="text-lg font-semibold text-slate-900 mb-2">No Payments Yet</h3>
                    <p className="text-slate-500">Your payment history will appear here</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {transactions.map((tx) => (
                      <div 
                        key={tx.id} 
                        className="flex items-center justify-between p-4 bg-slate-50 rounded-lg"
                      >
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                            <CreditCard className="w-5 h-5 text-blue-600" />
                          </div>
                          <div>
                            <p className="font-medium text-slate-900 capitalize">
                              {plans[tx.plan_id]?.name || tx.plan_id} Subscription
                            </p>
                            <p className="text-sm text-slate-500">
                              {formatDate(tx.created_at)}
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="font-archivo font-bold text-lg text-slate-900">
                            ${tx.amount.toFixed(2)} {tx.currency.toUpperCase()}
                          </p>
                          <Badge className={
                            tx.payment_status === 'paid' 
                              ? 'bg-emerald-100 text-emerald-700' 
                              : 'bg-amber-100 text-amber-700'
                          }>
                            {tx.payment_status}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
};

export default BillingPage;
