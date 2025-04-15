/**
 * Subscription management JavaScript
 * Handles all client-side interactions for the subscription page
 */
document.addEventListener('DOMContentLoaded', function() {
  // Initialize variables
  let selectedPlan = null;
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
  
  // Elements that need to be accessible throughout the script
  const subscriptionCards = document.querySelectorAll('.pricing-card');
  const loadingOverlay = document.getElementById('loading-overlay');
  const loadingMessage = document.getElementById('loading-message');
  const alertsContainer = document.getElementById('alerts-container');
  
  /**
   * Set up event listeners for plan selection
   */
  function initPlanSelection() {
    // Add click handlers to all plan buttons
    document.querySelectorAll('.select-plan-btn').forEach(button => {
      button.addEventListener('click', function(e) {
        e.preventDefault();
        const planId = this.getAttribute('data-plan-id');
        const planCard = this.closest('.pricing-card');
        
        if (!planId || !planCard) {
          showError('Could not determine selected plan');
          return;
        }
        
        // Update visual selection
        subscriptionCards.forEach(c => c.classList.remove('selected-plan'));
        planCard.classList.add('selected-plan');
        
        // Store selected plan data
        selectedPlan = {
          id: planId,
          name: planCard.querySelector('.pricing-header').textContent,
          price: planCard.querySelector('.pricing-price').textContent.trim()
        };
        
        // Proceed with payment initiation
        initiatePayment(planId);
      });
    });
    
    // Handle "Change Plan" button click
    const changeSubscriptionBtn = document.getElementById('changeSubscriptionBtn');
    if (changeSubscriptionBtn) {
      changeSubscriptionBtn.addEventListener('click', function() {
        // Scroll to Available Plans section
        const plansSection = document.querySelector('.dashboard-card h4:contains("Available Plans")');
        if (plansSection) {
          plansSection.closest('.dashboard-card').scrollIntoView({ behavior: 'smooth' });
        } else {
          window.scrollTo({
            top: document.querySelector('.row.mb-4:nth-child(3)').offsetTop,
            behavior: 'smooth'
          });
        }
      });
    }
    
    // Handle "Select Plan" button for inactive users
    const selectPlanBtn = document.getElementById('selectPlanBtn');
    if (selectPlanBtn) {
      selectPlanBtn.addEventListener('click', function() {
        // Scroll to Available Plans section
        const plansSection = document.querySelector('#available-plans-section');
        if (plansSection) {
          plansSection.scrollIntoView({ behavior: 'smooth' });
        } else {
          window.scrollTo({
            top: document.querySelector('.row.mb-4:nth-child(3)').offsetTop,
            behavior: 'smooth'
          });
        }
      });
    }
    
    // Handle billing period toggle
    const billingToggle = document.getElementById('billing-period-toggle');
    if (billingToggle) {
      billingToggle.addEventListener('change', function() {
        const isYearly = this.checked;
        updatePriceDisplay(isYearly);
      });
    }
  }
  
  /**
   * Update price display between monthly and yearly billing
   */
  function updatePriceDisplay(isYearly) {
    subscriptionCards.forEach(card => {
      const priceElement = card.querySelector('.pricing-price');
      const monthlyPrice = card.getAttribute('data-monthly-price');
      const yearlyPrice = card.getAttribute('data-yearly-price');
      
      if (priceElement && monthlyPrice && yearlyPrice) {
        if (isYearly) {
          priceElement.innerHTML = `$${yearlyPrice}<small class="text-muted">/year</small>`;
          // Update any save percentage display
          const savePercent = Math.round((1 - (yearlyPrice / (monthlyPrice * 12))) * 100);
          const saveBadge = card.querySelector('.save-badge');
          if (saveBadge) {
            saveBadge.textContent = `Save ${savePercent}%`;
            saveBadge.classList.remove('d-none');
          }
        } else {
          priceElement.innerHTML = `$${monthlyPrice}<small class="text-muted">/month</small>`;
          // Hide save percentage
          const saveBadge = card.querySelector('.save-badge');
          if (saveBadge) {
            saveBadge.classList.add('d-none');
          }
        }
      }
    });
  }
  
  /**
   * Initiate the payment process
   */
  function initiatePayment(planId) {
    if (!planId) {
      showError('Invalid plan selection');
      return;
    }
    
    // Show loading state
    showLoading('Preparing your subscription...');
    
    // Get billing period
    const billingToggle = document.getElementById('billing-period-toggle');
    const billingPeriod = billingToggle && billingToggle.checked ? 'yearly' : 'monthly';
    
    // Create order via API
    fetch('/api/subscription/create-order', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken || ''
      },
      body: JSON.stringify({
        planId: planId,
        billingPeriod: billingPeriod
      })
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      if (data.success && data.data && data.data.approvalUrl) {
        // Redirect to PayPal approval page
        window.location.href = data.data.approvalUrl;
      } else {
        // Show error message
        hideLoading();
        showError('Failed to create subscription order: ' + (data.message || 'Unknown error'));
      }
    })
    .catch(error => {
      console.error('Error:', error);
      hideLoading();
      showError('An error occurred while processing your request. Please try again.');
    });
  }
  
  /**
   * Cancel subscription API call
   */
  function cancelSubscription() {
    showLoading('Processing your request...');
    
    fetch('/api/subscription/cancel', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken || ''
      },
      body: JSON.stringify({})
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      hideLoading();
      
      if (data.success) {
        showSuccess(data.message || 'Subscription cancelled successfully');
        // Reload page after a delay
        setTimeout(() => {
          window.location.reload();
        }, 2000);
      } else {
        showError(data.message || 'Failed to cancel subscription');
      }
    })
    .catch(error => {
      console.error('Error:', error);
      hideLoading();
      showError('An error occurred while processing your request. Please try again.');
    });
  }
  
  /**
   * Set up cancel subscription modal
   */
  function initCancelSubscription() {
    const confirmCancelBtn = document.getElementById('confirmCancelSubscription');
    if (confirmCancelBtn) {
      confirmCancelBtn.addEventListener('click', function() {
        // Update button state
        this.disabled = true;
        this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
        
        // Call cancel API
        cancelSubscription();
        
        // Close modal (Bootstrap 5)
        const modal = bootstrap.Modal.getInstance(document.getElementById('cancelSubscriptionModal'));
        if (modal) {
          modal.hide();
        }
      });
    }
  }
  
  /**
   * Set up transaction details modal
   */
  function initTransactionDetails() {
    const transactionModal = document.getElementById('transactionDetailsModal');
    if (transactionModal) {
      transactionModal.addEventListener('show.bs.modal', function(event) {
        const button = event.relatedTarget;
        const transactionId = button.getAttribute('data-transaction-id');
        if (!transactionId) {
          return;
        }
        
        // Show loading state within modal
        const modalBody = this.querySelector('.modal-body');
        if (modalBody) {
          modalBody.innerHTML = `
            <div class="text-center p-4">
              <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
              </div>
              <p class="mt-2">Loading transaction details...</p>
            </div>
          `;
        }
        
        // Fetch transaction details
        fetch(`/api/user/transactions/${transactionId}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken || ''
          }
        })
        .then(response => {
          if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
          }
          return response.json();
        })
        .then(data => {
          if (data.success && data.data) {
            const tx = data.data;
            
            // Restore and update modal content
            modalBody.innerHTML = `
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Transaction ID:</strong></div>
                <div id="transaction-id">${tx.id || '---'}</div>
              </div>
              
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Date:</strong></div>
                <div id="transaction-date">${tx.date || '---'}</div>
              </div>
              
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Plan:</strong></div>
                <div id="transaction-plan">${tx.plan || '---'}</div>
              </div>
              
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Billing Period:</strong></div>
                <div id="transaction-billing">${tx.billing_period || '---'}</div>
              </div>
              
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Amount:</strong></div>
                <div id="transaction-amount">$${parseFloat(tx.amount).toFixed(2)}</div>
              </div>
              
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Payment Method:</strong></div>
                <div id="transaction-method">${getPaymentMethodDisplay(tx.payment_method)}</div>
              </div>
              
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Status:</strong></div>
                <div id="transaction-status">${getStatusBadge(tx.status)}</div>
              </div>
              
              <div class="d-flex justify-content-between mb-3">
                <div><strong>Payment ID:</strong></div>
                <div id="transaction-payment-id">${tx.payment_id || '---'}</div>
              </div>
            `;
            
            // Update receipt download button
            const receiptBtn = document.getElementById('downloadReceiptBtn');
            if (receiptBtn) {
              if (tx.status === 'completed') {
                receiptBtn.classList.remove('d-none');
                receiptBtn.href = `/dashboard/receipts/download/${tx.id}`;
              } else {
                receiptBtn.classList.add('d-none');
              }
            }
          } else {
            modalBody.innerHTML = `
              <div class="alert alert-danger">
                <i class="bi bi-exclamation-circle-fill me-2"></i>
                Failed to load transaction details: ${data.message || 'Unknown error'}
              </div>
            `;
          }
        })
        .catch(error => {
          console.error('Error fetching transaction details:', error);
          if (modalBody) {
            modalBody.innerHTML = `
              <div class="alert alert-danger">
                <i class="bi bi-exclamation-circle-fill me-2"></i>
                An error occurred while loading transaction details. Please try again.
              </div>
            `;
          }
        });
      });
    }
  }
  
  /**
   * Helper functions for UI interaction
   */
  function showLoading(message) {
    if (loadingOverlay) {
      if (loadingMessage) {
        loadingMessage.textContent = message || 'Loading...';
      }
      loadingOverlay.classList.remove('d-none');
    } else {
      // Fallback if custom loading overlay is not available
      document.body.classList.add('wait');
    }
  }
  
  function hideLoading() {
    if (loadingOverlay) {
      loadingOverlay.classList.add('d-none');
    }
    document.body.classList.remove('wait');
  }
  
  function showError(message) {
    if (alertsContainer) {
      const alertDiv = document.createElement('div');
      alertDiv.className = 'alert alert-danger alert-dismissible fade show';
      alertDiv.innerHTML = `
        <i class="bi bi-exclamation-circle-fill me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
      `;
      alertsContainer.appendChild(alertDiv);
      
      // Auto dismiss after 5 seconds
      setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 150);
      }, 5000);
    } else {
      // Fallback
      alert(message);
    }
  }
  
  function showSuccess(message) {
    if (alertsContainer) {
      const alertDiv = document.createElement('div');
      alertDiv.className = 'alert alert-success alert-dismissible fade show';
      alertDiv.innerHTML = `
        <i class="bi bi-check-circle-fill me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
      `;
      alertsContainer.appendChild(alertDiv);
      
      // Auto dismiss after 5 seconds
      setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 150);
      }, 5000);
    }
  }
  
  function getPaymentMethodDisplay(method) {
    switch (method) {
      case 'paypal':
        return '<i class="bi bi-paypal text-primary me-2"></i>PayPal';
      case 'credit_card':
        return '<i class="bi bi-credit-card text-success me-2"></i>Credit Card';
      case 'stripe':
        return '<i class="bi bi-credit-card text-info me-2"></i>Stripe';
      default:
        return method ? method.charAt(0).toUpperCase() + method.slice(1) : 'Unknown';
    }
  }
  
  function getStatusBadge(status) {
    let badgeClass = 'bg-secondary';
    
    switch (status) {
      case 'completed':
        badgeClass = 'bg-success';
        break;
      case 'pending':
        badgeClass = 'bg-warning';
        break;
      case 'failed':
        badgeClass = 'bg-danger';
        break;
      case 'refunded':
        badgeClass = 'bg-info';
        break;
    }
    
    return `<span class="badge ${badgeClass}">${status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown'}</span>`;
  }
  
  // Helper function for querySelector with contains
  // This is needed because "h4:contains()" is not standard
  Element.prototype.contains = function(text) {
    return this.textContent.includes(text);
  };
  
  // Initialize all components
  initPlanSelection();
  initCancelSubscription();
  initTransactionDetails();
});
