package com.sgarden.service;

import com.sgarden.dto.OrderRequest;
import com.sgarden.model.Order;
import com.sgarden.model.Product;
import com.sgarden.repository.OrderRepository;
import com.sgarden.repository.ProductRepository;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final ProductRepository productRepository;

    public OrderService(OrderRepository orderRepository, ProductRepository productRepository) {
        this.orderRepository = orderRepository;
        this.productRepository = productRepository;
    }

    public List<Order> getAllOrders() {
        return orderRepository.findAll();
    }

    public Optional<Order> getOrderById(String id) {
        return orderRepository.findById(id);
    }

    public Order createOrder(OrderRequest request) {
        List<Order.OrderItem> items = mapItems(request);

        Map<String, Integer> totalByProduct = new LinkedHashMap<>();
        for (Order.OrderItem item : items) {
            if (item.getProductId() == null || item.getQuantity() == null) {
                continue;
            }
            totalByProduct.merge(item.getProductId(), item.getQuantity(), Integer::sum);
        }

        Map<String, Product> reservedProducts = new LinkedHashMap<>();
        for (Map.Entry<String, Integer> entry : totalByProduct.entrySet()) {
            Optional<Product> productOpt = productRepository.findById(entry.getKey());
            if (productOpt.isEmpty()) {
                throw new InsufficientStockException("Product not found: " + entry.getKey());
            }
            Product product = productOpt.get();
            int currentStock = product.getStock() != null ? product.getStock() : 0;
            if (currentStock < entry.getValue()) {
                throw new InsufficientStockException(
                        "Insufficient stock for product: " + product.getName());
            }
            reservedProducts.put(entry.getKey(), product);
        }

        for (Map.Entry<String, Integer> entry : totalByProduct.entrySet()) {
            Product product = reservedProducts.get(entry.getKey());
            product.setStock(product.getStock() - entry.getValue());
            productRepository.save(product);
        }

        double total = calculateTotal(items);
        Order order = new Order();
        order.setItems(items);
        order.setTotal(total);
        return orderRepository.save(order);
    }

    public Optional<Order> updateOrder(String id, OrderRequest request) {
        return orderRepository.findById(id).map(order -> {
            if (request.getItems() != null) {
                List<Order.OrderItem> items = mapItems(request);
                order.setItems(items);
                order.setTotal(calculateTotal(items));
            }
            return orderRepository.save(order);
        });
    }

    public boolean deleteOrder(String id) {
        if (orderRepository.existsById(id)) {
            orderRepository.deleteById(id);
            return true;
        }
        return false;
    }

    private List<Order.OrderItem> mapItems(OrderRequest request) {
        List<Order.OrderItem> items = new ArrayList<>();
        if (request.getItems() == null) {
            return items;
        }
        for (OrderRequest.OrderItemRequest item : request.getItems()) {
            items.add(new Order.OrderItem(item.getProductId(), item.getQuantity()));
        }
        return items;
    }

    private double calculateTotal(List<Order.OrderItem> items) {
        double total = 0.0;
        for (Order.OrderItem item : items) {
            if (item.getProductId() == null || item.getQuantity() == null) {
                continue;
            }
            Optional<Product> product = productRepository.findById(item.getProductId());
            if (product.isPresent() && product.get().getPrice() != null) {
                total += product.get().getPrice() * item.getQuantity();
            }
        }
        return Math.round(total * 100.0) / 100.0;
    }
}
