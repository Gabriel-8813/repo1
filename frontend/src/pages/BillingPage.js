import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import {
  Truck, CreditCard, CheckCircle, DollarSign, LogOut,
  Percent, AlertTriangle, Receipt, Clock, FileText
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BillingPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, token, logout } = useAuth();
  const [balance, setBalance] = useState({ owed: 0, paid: 0, entries: [], currency: 'CAD' });
  const [fees, setFees] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [checkingPayment, setCheckingPayment] = useState(false);

  useEffect(() => {
    fetchData();
    checkPaymentStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const fetchData = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [b, f, t] = await Promise.all([
        axios.get(`${API}/driver/balance`, { headers }),
        axios.get(`${API}/fees/agreement`),
        axios.get(`${API}/payments/history`, { headers })
      ]);
      setBalance(b.data);
      setFees(f.data.agreement);
      setTransactions(t.data.transactions);
    } catch (e) {
      console.error(e);
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
        const r = await axios.get(`${API}/payments/status/${sessionId}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (r.data.payment_status === 'paid') {
          toast.success('Payment successful! Your balance has been cleared.');
          fetchData();
          navigate('/billing', { replace: true });
          setCheckingPayment(false);
          return;
        }
        if (r.data.status === 'expired') {
          toast.error('Payment session expired. Please try again.');
          navigate('/billing', { replace: true });
          setCheckingPayment(false);
          return;
        }
        attempts++;
        if (attempts < maxAttempts) setTimeout(poll, 2000);
        else {
          toast.info('Payment is being processed. Please check back in a moment.');
          setCheckingPayment(false);
        }
      } catch (err) {
        console.error(err);
        setCheckingPayment(false);
      }
    };
    poll();
  };

  const handlePayBalance = async () => {
    setPaying(true);
    try {
      const r = await axios.post(
        `${API}/payments/balance/checkout`,
        { origin_url: window.location.origin },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      window.location.href = r.data.checkout_url;
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to start checkout');
      setPaying(false);
    }
  };

  const handleLogout = () => { logout(); navigate('/'); };

  const formatDate = (iso) => new Date(iso).toLocaleString('en-CA', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  });

  if (loading || !fees) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="billing-page">
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
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
              {user?.role === 'admin' && <Link to="/admin" className="nav-link text-purple-700">Admin</Link>}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
            <LogOut className="w-4 h-4 mr-2" /> Logout
          </Button>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="font-archivo font-bold text-3xl text-slate-900">Billing & Commission</h1>
          <p className="text-slate-600 mt-1">Pay-as-you-earn — only pay commission on completed trips</p>
        </div>

        {checkingPayment && (
          <Card className="mb-8 border-blue-200 bg-blue-50">
            <CardContent className="p-6 flex items-center gap-4">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <div>
                <h3 className="font-semibold text-blue-900">Processing Payment</h3>
                <p className="text-blue-700 text-sm">Please wait while we verify your payment...</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Current Balance */}
        <Card className={`mb-8 border-2 ${balance.owed > 0 ? 'border-amber-300 bg-amber-50' : 'border-emerald-200 bg-emerald-50'}`}>
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${balance.owed > 0 ? 'bg-amber-100' : 'bg-emerald-100'}`}>
                  {balance.owed > 0
                    ? <AlertTriangle className="w-8 h-8 text-amber-600" />
                    : <CheckCircle className="w-8 h-8 text-emerald-600" />}
                </div>
                <div>
                  <h2 className="font-archivo font-bold text-xl text-slate-900">
                    {balance.owed > 0 ? 'Outstanding Balance' : 'All Clear'}
                  </h2>
                  <p className="text-slate-600 text-sm">
                    {balance.owed > 0
                      ? 'Commission + cancellation fees owed to the platform'
                      : 'You owe the platform nothing right now'}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="font-archivo font-black text-4xl text-slate-900" data-testid="balance-owed-amount">
                  ${balance.owed.toFixed(2)}
                </p>
                <p className="text-xs text-slate-500 mt-1">CAD · owed</p>
                {balance.owed > 0 && (
                  <Button
                    onClick={handlePayBalance}
                    disabled={paying}
                    className="mt-3 bg-blue-600 hover:bg-blue-700 rounded-full"
                    data-testid="pay-balance-btn"
                  >
                    <CreditCard className="w-4 h-4 mr-2" />
                    {paying ? 'Redirecting to Stripe...' : `Pay $${balance.owed.toFixed(2)} Now`}
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Commission Summary */}
        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center mb-4">
                <Percent className="w-6 h-6 text-blue-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">Commission Rate</p>
              <p className="font-archivo font-black text-3xl text-slate-900">
                {(fees.commission_rate * 100).toFixed(0)}%
              </p>
              <p className="text-xs text-slate-400 mt-1">of each completed trip</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center mb-4">
                <Clock className="w-6 h-6 text-amber-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">Cancellation Grace</p>
              <p className="font-archivo font-black text-3xl text-slate-900">
                {fees.cancellation_grace_minutes} min
              </p>
              <p className="text-xs text-slate-400 mt-1">free cancel after accepting</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-6">
              <div className="w-12 h-12 bg-red-100 rounded-xl flex items-center justify-center mb-4">
                <DollarSign className="w-6 h-6 text-red-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">Late Cancellation Fee</p>
              <p className="font-archivo font-black text-3xl text-slate-900">
                ${fees.cancellation_fee.toFixed(2)}
              </p>
              <p className="text-xs text-slate-400 mt-1">after grace window</p>
            </CardContent>
          </Card>
        </div>

        {/* Ledger */}
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] mb-8">
          <CardHeader>
            <CardTitle className="font-archivo flex items-center gap-2">
              <Receipt className="w-5 h-5" /> Commission & Fee Ledger
            </CardTitle>
          </CardHeader>
          <CardContent>
            {balance.entries.length === 0 ? (
              <div className="text-center py-12 text-slate-500">
                <Receipt className="w-12 h-12 mx-auto mb-4 text-slate-300" />
                <p>No commission activity yet</p>
                <p className="text-sm">Complete your first trip to see your ledger</p>
              </div>
            ) : (
              <div className="space-y-3">
                {balance.entries.map(e => (
                  <div key={e.id} className="flex items-center justify-between p-4 rounded-lg border border-slate-100" data-testid={`ledger-row-${e.id}`}>
                    <div className="flex items-center gap-3">
                      <Badge className={e.type === 'commission' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'}>
                        {e.type === 'commission' ? 'Commission' : 'Cancellation'}
                      </Badge>
                      <div>
                        <p className="text-sm font-medium text-slate-900">{e.description}</p>
                        <p className="text-xs text-slate-500">{formatDate(e.created_at)}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-archivo font-bold text-lg text-slate-900">${e.amount.toFixed(2)}</p>
                      <Badge className={e.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}>
                        {e.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Fee Agreement */}
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] mb-8">
          <CardHeader>
            <CardTitle className="font-archivo flex items-center gap-2">
              <FileText className="w-5 h-5" /> Agreed Platform Fees
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <FeeRow label="Base Rate per KM" value={`$${fees.base_rate_per_km.toFixed(2)} CAD`} />
              <FeeRow label="Minimum Trip Fee" value={`$${fees.minimum_fee.toFixed(2)} CAD`} />
              <FeeRow label="Urgent Multiplier" value={`${fees.urgent_multiplier}×`} />
              <FeeRow label="Emergency Multiplier" value={`${fees.emergency_multiplier}×`} />
              <FeeRow label="Temperature-Controlled Add-on" value={`$${fees.temperature_controlled_fee.toFixed(2)} CAD`} />
              <FeeRow label="Platform Commission" value={`${(fees.commission_rate * 100).toFixed(0)}% of completed trip`} />
              <FeeRow label="Cancellation Grace Window" value={`${fees.cancellation_grace_minutes} minutes`} />
              <FeeRow label="Late Cancellation Fee" value={`$${fees.cancellation_fee.toFixed(2)} CAD`} />
            </div>
            <p className="mt-6 text-xs text-slate-500">
              By using MediTrans you agree to the commission-based revenue model. The platform deducts {(fees.commission_rate * 100).toFixed(0)}% of every completed trip and charges a ${fees.cancellation_fee.toFixed(2)} fee for cancellations made more than {fees.cancellation_grace_minutes} minutes after accepting a trip.
            </p>
          </CardContent>
        </Card>

        {/* Payment History */}
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardHeader>
            <CardTitle className="font-archivo">Payment History</CardTitle>
          </CardHeader>
          <CardContent>
            {transactions.length === 0 ? (
              <p className="text-center py-8 text-slate-500 text-sm">No payments yet</p>
            ) : (
              <div className="space-y-2">
                {transactions.map(tx => (
                  <div key={tx.id} className="flex items-center justify-between p-3 rounded border border-slate-100 text-sm">
                    <div>
                      <p className="font-medium">${tx.amount?.toFixed(2)} {tx.currency?.toUpperCase()}</p>
                      <p className="text-xs text-slate-500">{formatDate(tx.created_at)}</p>
                    </div>
                    <Badge className={tx.payment_status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}>
                      {tx.payment_status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

const FeeRow = ({ label, value }) => (
  <div className="flex items-center justify-between p-3 rounded bg-slate-50 border border-slate-100">
    <span className="text-slate-600">{label}</span>
    <span className="font-semibold text-slate-900">{value}</span>
  </div>
);

export default BillingPage;
